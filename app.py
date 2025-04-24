import os
import time
import zipfile

import pydicom
from flask import Flask, render_template, request, send_from_directory
from PIL import Image
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'extracted_images'
ALLOWED_EXTENSIONS = {'zip'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_dicom_to_png(dicom_path, output_dir):
    """
    Extracts pixel data from a DICOM file and saves it as a PNG image.
    The output filename is based on the DICOM's Instance Number if available,
    otherwise it defaults to the original filename.

    Args:
        dicom_path (str): Path to the input DICOM file.
        output_dir (str): Path to the directory where the PNG will be saved.

    Returns:
        bool: True if the extraction was successful, False otherwise.
    """
    try:
        dataset = pydicom.dcmread(dicom_path)
        if 'PixelData' in dataset:
            pixel_array = dataset.pixel_array
            if len(pixel_array.shape) == 3:
                # Handle color images (e.g., RGB)
                image = Image.fromarray(pixel_array, 'RGB')
            elif len(pixel_array.shape) == 2:
                # Handle grayscale images
                image = Image.fromarray(pixel_array).convert('L')
            else:
                print(f"Unsupported pixel array shape: {pixel_array.shape} in {dicom_path}")
                return None

            # Try to use the Instance Number for ordered filenames
            if 'InstanceNumber' in dataset:
                instance_number = str(dataset.InstanceNumber).zfill(6)  # Pad with zeros for consistent sorting
                filename = f"{instance_number}.png"
            else:
                filename = os.path.basename(dicom_path).rsplit('.', 1)[0] + '.png'

            output_path = os.path.join(output_dir, filename)
            image.save(output_path)
            print(f"Extracted: {dicom_path} -> {output_path}")
            return True
        else:
            print(f"No PixelData found in: {dicom_path}")
            return False
    except Exception as e:
        print(f"Error processing {dicom_path}: {e}")
        return False

def get_folder_description(folder_path):
    summary_path = os.path.join(folder_path, 'summary.txt')
    if os.path.exists(summary_path):
        try:
            with open(summary_path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            return f"Error reading summary: {e}"
    return "Summary not available yet."

def get_image_files(folder_path):
    return sorted([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f)) and f.lower().endswith(('.png'))])

@app.route('/', methods=['GET', 'POST'])
def index():
    extracted_image_path = os.path.join(os.getcwd(), app.config['OUTPUT_FOLDER'])
    main_folders = [d for d in os.listdir(extracted_image_path) if os.path.isdir(os.path.join(extracted_image_path, d))]
    folder_data = []
    for main_folder in main_folders:
        main_folder_path = os.path.join(extracted_image_path, main_folder)
        subfolders_data = []
        subfolders = [sub_d for sub_d in os.listdir(main_folder_path) if os.path.isdir(os.path.join(main_folder_path, sub_d))]
        for subfolder in subfolders:
            subfolder_path = os.path.join(main_folder_path, subfolder)
            description = get_folder_description(subfolder_path)
            images = get_image_files(subfolder_path)
            subfolders_data.append({'name': subfolder, 'description': description, 'images': images})

        description = get_folder_description(main_folder_path)
        images = get_image_files(main_folder_path)
        folder_data.append({'name': main_folder, 'description': description, 'subfolders': subfolders_data, 'images': images})

    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('index.html', error='No file part', folders=folder_data)
        file = request.files['file']
        if file.filename == '':
            return render_template('index.html', error='No selected file', folders=folder_data)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            output_folder_base = app.config['OUTPUT_FOLDER']

            try:
                with zipfile.ZipFile(filepath, 'r') as zip_ref:
                    if not zip_ref.namelist():
                        return render_template('index.html', error='Zip file is empty.', folders=folder_data)

                    series_output_folders = {}

                    for member in zip_ref.namelist():
                        if not os.path.isdir(member):
                            try:
                                with zip_ref.open(member) as dicom_file:
                                    temp_dicom_path = os.path.join(app.config['UPLOAD_FOLDER'], "temp_uid_" + os.path.basename(member))
                                    with open(temp_dicom_path, 'wb') as f:
                                        f.write(dicom_file.read())
                                    try:
                                        dataset = pydicom.dcmread(temp_dicom_path)
                                        patient_name = dataset.PatientName if 'PatientName' in dataset else "UnknownPatient"
                                        study_id = dataset.StudyID if 'StudyID' in dataset else "UnknownStudyID"
                                        series_uid = dataset.SeriesInstanceUID if 'SeriesInstanceUID' in dataset else "UnknownSeriesUID"
                                        sanitized_patient_name = "".join(c if c.isalnum() else "_" for c in patient_name)
                                        sanitized_study_id = "".join(c if c.isalnum() else "_" for c in study_id)
                                        sanitized_series_uid = "".join(c if c.isalnum() else "_" for c in series_uid)
                                        series_base_folder = os.path.join(output_folder_base, f"{sanitized_patient_name}_{sanitized_study_id}")
                                        series_output_path = os.path.join(series_base_folder, sanitized_series_uid)
                                        series_output_folders[member] = series_output_path
                                        os.makedirs(series_output_path, exist_ok=True)
                                    except Exception as e:
                                        print(f"Error reading DICOM header from {member} (UID): {e}")
                                        fallback_folder = os.path.join(output_folder_base, "unknown_series_" + str(int(time.time())))
                                        series_output_folders[member] = fallback_folder
                                        os.makedirs(fallback_folder, exist_ok=True)
                                    finally:
                                        os.remove(temp_dicom_path)
                            except Exception as e:
                                print(f"Error opening member {member} for UID reading: {e}")

                    for member in zip_ref.namelist():
                        if not os.path.isdir(member):
                            try:
                                with zip_ref.open(member) as dicom_file:
                                    temp_dicom_path = os.path.join(app.config['UPLOAD_FOLDER'], "temp_extract_" + os.path.basename(member))
                                    with open(temp_dicom_path, 'wb') as f:
                                        f.write(dicom_file.read())
                                    extract_dicom_to_png(temp_dicom_path, series_output_folders[member])
                                    os.remove(temp_dicom_path)
                            except Exception as e:
                                print(f"Error processing member {member} for extraction: {e}")

                    # Re-generate folder data after extraction to include images
                    extracted_image_path = os.path.join(os.getcwd(), app.config['OUTPUT_FOLDER'])
                    main_folders = [d for d in os.listdir(extracted_image_path) if os.path.isdir(os.path.join(extracted_image_path, d))]
                    folder_data = []
                    for main_folder in main_folders:
                        main_folder_path = os.path.join(extracted_image_path, main_folder)
                        subfolders_data = []
                        subfolders = [sub_d for sub_d in os.listdir(main_folder_path) if os.path.isdir(os.path.join(main_folder_path, sub_d))]
                        for subfolder in subfolders:
                            subfolder_path = os.path.join(main_folder_path, subfolder)
                            description = get_folder_description(subfolder_path)
                            images = get_image_files(subfolder_path)
                            subfolders_data.append({'name': subfolder, 'description': description, 'images': images})

                        description = get_folder_description(main_folder_path)
                        images = get_image_files(main_folder_path)
                        folder_data.append({'name': main_folder, 'description': description, 'subfolders': subfolders_data, 'images': images})

                    return render_template('index.html', success=f'Successfully extracted images to series folders in: {os.path.basename(output_folder_base)}', folders=folder_data)

            except zipfile.BadZipFile:
                return render_template('index.html', error='Invalid zip file', folders=folder_data)
            except Exception as e:
                return render_template('index.html', error=f'Error extracting zip file: {e}', folders=folder_data)
            finally:
                os.remove(filepath)

    return render_template('index.html', folders=folder_data)

@app.route('/extracted_images/<path:folder>')
def show_images(folder):
    folder_path = os.path.join(app.config['OUTPUT_FOLDER'], folder)
    if not os.path.isdir(folder_path):
        return render_template('error.html', message='Folder not found.')
    image_files = get_image_files(folder_path)
    return render_template('images.html', folder=folder, images=image_files)

@app.route('/extracted_images/<folder>/<filename>')
def download_image(folder, filename):
    return send_from_directory(os.path.join(app.config['OUTPUT_FOLDER'], folder), filename)

# New route to directly serve the specific image
@app.route('/extracted_image/<path:image_path>')
def serve_specific_image(image_path):
    full_image_path = os.path.join(app.config['OUTPUT_FOLDER'], image_path)
    image_directory = os.path.dirname(full_image_path)
    image_filename = os.path.basename(full_image_path)
    if os.path.isfile(full_image_path):
        return send_from_directory(image_directory, image_filename)
    else:
        return render_template('error.html', message='Image not found.')

if __name__ == '__main__':
    app.run(debug=True)