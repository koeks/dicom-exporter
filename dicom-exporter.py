<!DOCTYPE html>
<html>
<head>
    <title>DICOM to PNG Converter</title>
    <style>
        body {
            font-family: sans-serif;
            margin: 20px;
        }
        .container {
            width: 400px;
            margin: 0 auto;
        }
        input[type="file"] {
            display: block;
            margin-bottom: 10px;
        }
        button {
            padding: 10px 20px;
            background-color: #007bff;
            color: white;
            border: none;
            cursor: pointer;
        }
        #status {
            margin-top: 10px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>DICOM to PNG Converter</h1>
        <input type="file" id="dicomFile" accept=".dcm, .dicom">
        <button onclick="uploadFile()">Convert to PNG</button>
        <div id="status"></div>
    </div>

    <script>
        async function uploadFile() {
            const fileInput = document.getElementById('dicomFile');
            const statusDiv = document.getElementById('status');
            const file = fileInput.files[0];

            if (!file) {
                statusDiv.textContent = 'Please select a DICOM file.';
                return;
            }

            statusDiv.textContent = 'Uploading and processing...';

            const formData = new FormData();
            formData.append('dicom_file', file);

            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });

                if (response.ok) {
                    const data = await response.json();
                    statusDiv.textContent = data.message;
                    if (data.folder_name) {
                        statusDiv.innerHTML += `<br>PNG images saved in folder: <a href="/download/${data.folder_name}" target="_blank">${data.folder_name}</a>`;
                    }
                } else {
                    const errorData = await response.json();
                    statusDiv.textContent = `Error: ${errorData.error || 'Failed to process file.'}`;
                }
            } catch (error) {
                statusDiv.textContent = `Network error: ${error.message}`;
            }
        }
    </script>

    <script>
        from http.server import HTTPServer, BaseHTTPRequestHandler
        from http import HTTPStatus
        import cgi
        import os
        import pydicom
        from PIL import Image
        import numpy as np
        import time
        import shutil
        import json
        from urllib.parse import quote

        UPLOAD_DIR = 'uploads'
        OUTPUT_BASE_DIR = 'output'

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

        class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/download/'):
                    folder_name = self.path.split('/')[-1]
                    output_path = os.path.join(OUTPUT_BASE_DIR, folder_name)

                    if os.path.exists(output_path) and os.path.isdir(output_path):
                        self.send_response(HTTPStatus.OK)
                        self.send_header('Content-type', 'application/zip')
                        self.send_header('Content-Disposition', f'attachment; filename="{folder_name}.zip"')
                        self.end_headers()

                        shutil.make_archive(os.path.join(OUTPUT_BASE_DIR, folder_name), 'zip', output_path)
                        with open(f'{os.path.join(OUTPUT_BASE_DIR, folder_name)}.zip', 'rb') as f:
                            shutil.copyfileobj(f, self.wfile)
                        os.remove(f'{os.path.join(OUTPUT_BASE_DIR, folder_name)}.zip')
                    else:
                        self.send_response(HTTPStatus.NOT_FOUND)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(b'Folder not found.')
                    return
                elif self.path == '/':
                    self.send_response(HTTPStatus.OK)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    with open(__file__, 'rb') as f:
                        self.wfile.write(f.read())
                    return
                else:
                    self.send_response(HTTPStatus.NOT_FOUND)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'Not Found')

            def do_POST(self):
                if self.path == '/upload':
                    form = cgi.FieldStorage(
                        fp=self.rfile,
                        headers=self.headers,
                        environ={'REQUEST_METHOD': 'POST'}
                    )
                    dicom_file = form.getvalue('dicom_file')
                    file_item = form['dicom_file']

                    if file_item and file_item.filename:
                        timestamp = str(int(time.time()))
                        output_folder = os.path.join(OUTPUT_BASE_DIR, timestamp)
                        os.makedirs(output_folder, exist_ok=True)
                        file_path = os.path.join(UPLOAD_DIR, file_item.filename)

                        try:
                            with open(file_path, 'wb') as f:
                                f.write(file_item.file.read())

                            dataset = pydicom.dcmread(file_path)
                            if 'pixel_array' in dataset:
                                pixel_array = dataset.pixel_array
                                if len(pixel_array.shape) == 3:
                                    for i, frame in enumerate(pixel_array):
                                        image = Image.fromarray(frame.astype(np.uint8))
                                        png_path = os.path.join(output_folder, f'frame_{i+1}.png')
                                        image.save(png_path)
                                elif len(pixel_array.shape) == 2:
                                    image = Image.fromarray(pixel_array.astype(np.uint8))
                                    png_path = os.path.join(output_folder, 'image.png')
                                    image.save(png_path)
                                else:
                                    self._send_json_response(HTTPStatus.OK, {'message': 'DICOM file processed, but no recognizable image data found.'})
                                    os.remove(file_path)
                                    return

                                self._send_json_response(HTTPStatus.OK, {'message': 'DICOM file successfully processed.', 'folder_name': timestamp})
                            else:
                                self._send_json_response(HTTPStatus.BAD_REQUEST, {'error': 'DICOM file does not contain pixel data.'})
                        except Exception as e:
                            self._send_json_response(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
                        finally:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        return
                    else:
                        self._send_json_response(HTTPStatus.BAD_REQUEST, {'error': 'No file uploaded.'})
                        return
                else:
                    self.send_response(HTTPStatus.NOT_FOUND)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'Not Found')

            def _send_json_response(self, status_code, data):
                self.send_response(status_code)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                json_data = json.dumps(data).encode('utf-8')
                self.wfile.write(json_data)

        if __name__ == '__main__':
            server_address = ('', 8000)
            httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
            print('Server running on http://localhost:8000...')
            httpd.serve_forever()
    </script>
</body>
</html>