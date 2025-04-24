import os
import time

import chardet
import google.generativeai as genai
import openai
from fpdf import FPDF
from PIL import Image

# --- API Keys ---


GOOGLE_API_KEY = "API_KEY"


genai.configure(api_key=GOOGLE_API_KEY)


openai.api_key = "API_KEY"


main_image_dir = os.path.join(os.getcwd(), "extracted_images", "")

# Define model_name BEFORE using it
model_name = 'gemini-2.0-flash'

combined_pdf_file_path = os.path.join(main_image_dir, f"combined_summary_{model_name.replace('-', '_')}.pdf")
combined_analysis_file_path = os.path.join(main_image_dir, f"combined_analysis_{model_name.replace('-', '_')}.txt")
final_summary_path_txt = os.path.join(main_image_dir, f"summary_{model_name.replace('-', '_')}.txt")


model = genai.GenerativeModel(model_name)


#symptoms = "Patient symptoms experienced: Right side of body numb."
symptoms = ""

combined_summary_content = ""
all_combined_analysis_content = ""


# Define font paths (adjust these based on where the TTF files are)
unicode_font_path = 'NotoSans-Regular.ttf'  # Using Noto Sans as a Unicode font


def read_file_with_fallback(path):
    with open(path, 'rb') as f:
        raw_data = f.read()
    detected = chardet.detect(raw_data)
    encoding = detected['encoding'] or 'utf-8'
    return raw_data.decode(encoding, errors='replace')


def process_and_save_image(filepath, folder_path):
    filename = os.path.basename(filepath)
    output_filename = os.path.join(folder_path, f"{os.path.splitext(filename)[0]}_analysis_{model_name.replace('-', '_')}.txt")

    if os.path.exists(output_filename) and os.path.getsize(output_filename) > 0:
        print(f"DEBUG: Analysis file already exists and is not blank for {filename} in {os.path.basename(folder_path)}. Skipping.")
        return

    try:
        img = Image.open(filepath)
        prompt = f"Analyze this medical image for any visible abnormalities, asymmetries, or deviations from expected anatomy. Describe any findings that might suggest a potential medical issue, keeping in mind that further clinical correlation is necessary for diagnosis. Do not give any disclaimers. Give a probability of correctness. {symptoms} {filename} in {os.path.basename(folder_path)}"
        response = model.generate_content([prompt, img])
        analysis_text = response.text
        print(f"--- Analysis for {filename} in {os.path.basename(folder_path)} ---")
        print(analysis_text)
        print("\n")

        try:
            with open(output_filename, 'w') as outfile:
                outfile.write(analysis_text)
            print(f"Analysis for {filename} saved to: {output_filename}\n")
        except Exception as e:
            print(f"DEBUG: Error saving analysis for {filename} to {output_filename}: {e}\n")

    except Exception as e:
        print(f"DEBUG: Error processing {filename} in {os.path.basename(folder_path)}: {e}")
        time.sleep(10)


# Initialize the combined analysis file at the beginning to ensure overwriting
try:
    with open(combined_analysis_file_path, 'w', encoding='utf-8') as outfile:
        outfile.write("")
    print(f"DEBUG: Initialized (overwrote if existing) combined analysis file at: {combined_analysis_file_path}")
except Exception as e:
    print(f"DEBUG: Error initializing combined analysis file: {e}")

# Initialize the final summary file at the beginning to ensure overwriting
try:
    with open(final_summary_path_txt, 'w', encoding='utf-8') as outfile:
        outfile.write("")
    print(f"DEBUG: Initialized (overwrote if existing) final summary file at: {final_summary_path_txt}")
    combined_summary_content = "" # Reset the in-memory content as well
except Exception as e:
    print(f"DEBUG: Error initializing final summary file: {e}")


for root, _, files in os.walk(main_image_dir, topdown=False):
    print(f"DEBUG: Processing folder: {root}")

    all_analysis_files = [
        f for f in os.listdir(root)
        if f.endswith(f"_analysis_{model_name.replace('-', '_')}.txt")
    ]
    if all_analysis_files:
        for analysis_file in all_analysis_files:
            analysis_file_path = os.path.join(root, analysis_file)
            try:
                content = read_file_with_fallback(analysis_file_path)
                all_combined_analysis_content += f"--- Content from: {os.path.basename(root)}/{analysis_file} ---\n{content}\n\n--------------------\n\n"
                print(f"DEBUG: Combined content of {analysis_file} from {os.path.basename(root)}.")
            except Exception as e:
                print(f"DEBUG: Error reading {analysis_file}: {e}")

        summary_output_path = os.path.join(root, f"summary_{model_name.replace('-', '_')}.txt")
        pdf_output_path = os.path.join(root, f"summary_{model_name.replace('-', '_')}.pdf")

        if os.path.exists(summary_output_path) and os.path.getsize(summary_output_path) > 0:
            print(f"DEBUG: Summary file exists at {summary_output_path}. Proceeding with PDF creation/recreation.")
            try:
                text_content = read_file_with_fallback(summary_output_path)
                combined_summary_content += f"\n--- Summary for {os.path.basename(root)} ---\n{text_content}\n"
            except Exception as e:
                print(f"DEBUG: Error reading summary file: {e}")

            # Create PDF
            pdf = FPDF()
            pdf.add_page()
            try:
                pdf.add_font('NotoSans', '', unicode_font_path)
                pdf.set_font('NotoSans', '', 8)
            except Exception as e:
                print(f"DEBUG: Error loading Unicode font: {e}")
                pdf.set_font("Helvetica", size=8)

            lines = text_content.split('\n')
            line_height = pdf.font_size * 1.5

            for line in lines:
                if line.strip():
                    try:
                        pdf.cell(0, line_height, line, ln=1, align='L')
                    except Exception as e:
                        encoded_line = line.encode('latin-1', 'ignore').decode('latin-1')
                        pdf.cell(0, line_height, encoded_line, ln=1, align='L')

            pdf.output(pdf_output_path, 'F')
            print(f"DEBUG: Successfully created/recreated PDF summary: '{pdf_output_path}'")

        else:
            # Generate summary only if there were analysis files in this directory
            if all_analysis_files:
                analysis_content_for_summary = ""
                for af in all_analysis_files:
                    af_path = os.path.join(root, af)
                    try:
                        analysis_content_for_summary += read_file_with_fallback(af_path) + "\n\n--------------------\n\n"
                    except Exception as e:
                        print(f"DEBUG: Error reading {af} for summary generation: {e}")

                prompt_summary = f"Synthesize the key observations derived from the provided medical image analysis. Clearly highlight any identified abnormalities, precisely specify their locations within the image(s), and articulate the potential clinical implications of these findings using clear and concise language. Ensure that each abnormality and its associated details are presented distinctly. Give a probability for each. Do not give any disclaimers. :\n\n{analysis_content_for_summary}"
                try:
                    print(f"DEBUG: Generating Gemini summary for: {os.path.basename(root)}")
                    summary_response = model.generate_content([prompt_summary])
                    summary_text = summary_response.text
                    summary_output_path = os.path.join(root, f"summary_{model_name.replace('-', '_')}.txt")
                    with open(summary_output_path, 'w') as outfile_summary:
                        outfile_summary.write(summary_text)
                    print(f"DEBUG: Generated summary and saved to: {summary_output_path}\n")

                    combined_summary_content += f"\n--- Summary for {os.path.basename(root)} ---\n{summary_text}\n"

                    text_content = read_file_with_fallback(summary_output_path)

                    pdf = FPDF()
                    pdf.add_page()
                    try:
                        pdf.add_font('NotoSans', '', unicode_font_path)
                        pdf.set_font('NotoSans', '', 8)
                    except Exception as e:
                        print(f"DEBUG: Error loading Unicode font: {e}")
                        pdf.set_font("Helvetica", size=8)

                    lines = text_content.split('\n')
                    line_height = pdf.font_size * 1.5

                    for line in lines:
                        if line.strip():
                            try:
                                pdf.cell(0, line_height, line, ln=1, align='L')
                            except Exception as e:
                                encoded_line = line.encode('latin-1', 'ignore').decode('latin-1')
                                pdf.cell(0, line_height, encoded_line, new_x="LMARGIN", new_y="NEXT", align='L')

                    pdf_output_path = os.path.join(root, f"summary_{model_name.replace('-', '_')}.pdf")
                    pdf.output(pdf_output_path, 'F')
                    print(f"DEBUG: Successfully created/recreated PDF summary: '{pdf_output_path}'")

                except Exception as e:
                    print(f"DEBUG: Error generating or saving summary: {e}\n")

# After the loop, write the combined analysis content to the top-level file
try:
    with open(combined_analysis_file_path, 'w', encoding='utf-8') as outfile:
        outfile.write(all_combined_analysis_content)
    print(f"DEBUG: Successfully created combined analysis file at: {combined_analysis_file_path}")
except Exception as e:
    print(f"DEBUG: Error writing to combined analysis file: {e}")


final_summary_path_txt = os.path.join(main_image_dir, f"summary_{model_name.replace('-', '_')}.txt")

try:
    # Writing the combined summary content to a text file
    with open(final_summary_path_txt, 'w', encoding='utf-8') as final_summary_file:
        final_summary_file.write(combined_summary_content)
    print(f"DEBUG: Successfully wrote combined summary content to: {final_summary_path_txt}")

    # Reading the content from the text file for PDF generation
    with open(final_summary_path_txt, 'r', encoding='utf-8') as final_summary_file:
        text_content = final_summary_file.read()

    # Check if the text content is empty and print a warning if so
    if not text_content.strip():
        print(f"Warning: The text content from {final_summary_path_txt} is empty. Skipping combined PDF generation.")
    else:
        # Create a new PDF document for the combined summary
        pdf = FPDF()
        pdf.add_page()

        # Set up font (adding fallback for Unicode font)
        try:
            pdf.add_font('NotoSans', '', unicode_font_path)
            pdf.set_font('NotoSans', '', 8)
        except Exception as e:
            print(f"Error loading Unicode font: {e}")
            pdf.set_font("Helvetica", size=8)  # Fallback to Helvetica

        # Split the text content into lines
        lines = text_content.split('\n')
        line_height = pdf.font_size * 1.5

        # Add each line to the PDF, handling potential encoding issues
        for line in lines:
            if line.strip():  # Only add non-empty lines
                try:
                    pdf.cell(0, line_height, line, new_x="LMARGIN", new_y="NEXT", align='L')
                except Exception as e:
                    print(f"Error writing line to combined PDF: {e}")
                    encoded_line = line.encode('latin-1', 'ignore').decode('latin-1')
                    pdf.cell(0, line_height, encoded_line, new_x="LMARGIN", new_y="NEXT", align='L')

        # Define the output path for the combined PDF
        pdf_output_path = os.path.join(main_image_dir, f"combined_summary_{model_name.replace('-', '_')}.pdf")
        pdf.output(pdf_output_path)
        print(f"Successfully created the combined PDF summary file: '{pdf_output_path}'")

except FileNotFoundError:
    print(f"Error: The file '{final_summary_path_txt}' was not found for combined PDF conversion.")
except Exception as e:
    print(f"An error occurred during combined PDF conversion: {e}")


# --- Gemini API Request to Analyze the Final Summary ---
final_summary_file_path = os.path.join(main_image_dir, f"summary_{model_name.replace('-', '_')}.txt")

try:
    with open(final_summary_file_path, 'r', encoding='utf-8') as f:
        summary_content = f.read()

    prompt_analyze = f"Analyze the provided medical summaries and synthesize the key observations. Identify and describe all abnormalities with precise anatomical locations, and explain the potential clinical implications of each finding in clear, concise language. Present each abnormality separately, assigning a probability to each. Avoid any disclaimers or use of tables. :\n\n{summary_content}"
    analyze_response = model.generate_content([prompt_analyze])
    analysis_result = analyze_response.text
    #print(prompt_analyze)
    #print("\n--- Gemini Analysis of Final Summary ---")
    #print(analysis_result)

    analysis_output_path = os.path.join(main_image_dir, f"analysis_of_summary_{model_name.replace('-', '_')}.txt")
    with open(analysis_output_path, 'w', encoding='utf-8') as outfile:
        outfile.write(analysis_result)
    print(f"\nGemini's analysis of the final summary saved to: {analysis_output_path}")

except FileNotFoundError:
    print(f"Error: Final summary file not found at: {final_summary_file_path}")
except Exception as e:
    print(f"An error occurred during the Gemini analysis request: {e}")

print("Processing complete.")