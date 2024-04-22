import sys
import json
import requests
import base64
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLineEdit, QTextEdit, QLabel, QMessageBox, QInputDialog,
                             QComboBox, QFileDialog)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
from replicate import get_docker_commands
from runpod_utils import create_pod
import runpod
from dotenv import load_dotenv
import os

def load_tokens():
    load_dotenv()
    runpod_token = os.getenv('RUNPOD_TOKEN')
    hf_token = os.getenv('HF_TOKEN')
    runpod.api_key = runpod_token
    return runpod_token, hf_token

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.runpod_token, self.hf_token = load_tokens()
        self.pod_url = None  # Initialize the pod_url
        self.current_pixmap = None  # Initialize the pixmap
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Replicate to RunPod App')
        self.setGeometry(100, 100, 1200, 600)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        # Input and buttons on left panel
        left_panel.addWidget(QLabel('Enter the Replicate URL:'))
        self.url_input = QLineEdit(self)
        left_panel.addWidget(self.url_input)

        left_panel.addWidget(QLabel('Enter HF Token:'))
        self.hf_token_input = QLineEdit(self)
        # Set the token fields after they have been initialized
        self.hf_token_input.setText("•" * (len(self.hf_token) - 4) + self.hf_token[-4:])
        left_panel.addWidget(self.hf_token_input)

        left_panel.addWidget(QLabel('Enter RunPod Token:'))
        self.runpod_token_input = QLineEdit(self)
        self.runpod_token_input.setText("•" * (len(self.runpod_token) - 4) + self.runpod_token[-4:])
        left_panel.addWidget(self.runpod_token_input)

        left_panel.addWidget(QLabel('Select GPU Type:'))
        self.gpu_type_combo = QComboBox(self)
        self.populate_gpu_types()
        left_panel.addWidget(self.gpu_type_combo)

        fetch_button = QPushButton('Fetch and Create Pod', self)
        fetch_button.clicked.connect(self.fetch_and_create_pod)
        left_panel.addWidget(fetch_button)

        self.json_editor = QTextEdit(self)
        self.json_editor.setPlaceholderText("Enter JSON here...")
        left_panel.addWidget(self.json_editor)

        send_request_button = QPushButton('Send Custom Request', self)
        send_request_button.clicked.connect(self.send_custom_request)
        left_panel.addWidget(send_request_button)

        # Output on right panel
        self.output_display = QTextEdit(self)
        self.output_display.setReadOnly(True)
        right_panel.addWidget(self.output_display)

        self.image_label = QLabel(self)
        self.image_label.setFixedSize(400, 400)
        self.image_label.mousePressEvent = self.save_image
        right_panel.addWidget(self.image_label)

        main_layout.addLayout(left_panel, 1)
        main_layout.addLayout(right_panel, 1)

    def populate_gpu_types(self):
        gpu_types = [
            ("NVIDIA H100 80GB PCIe", "H100 80GB PCIe"),
            ("NVIDIA H100 80GB HBM3", "H100 80GB SXM5"),
            ("NVIDIA L40", "L40"),
            ("NVIDIA L40S", "L40S"),
            ("NVIDIA RTX 6000 Ada Generation", "RTX 6000 Ada"),
            ("NVIDIA GeForce RTX 4090", "RTX 4090"),
            ("NVIDIA L4", "L4"),
            ("NVIDIA RTX 4000 Ada Generation", "RTX 4000 Ada"),
            # Previous generation GPUs supported by secure cloud
            ("NVIDIA A100 80GB PCIe", "A100 80GB"),
            ("NVIDIA A100-SXM4-80GB", "A100 SXM 80GB"),
            ("NVIDIA A40", "A40"),
            ("NVIDIA RTX A6000", "RTX A6000"),
            ("NVIDIA GeForce RTX 3090", "RTX 3090"),
            ("NVIDIA RTX A5000", "RTX A5000"),
            ("NVIDIA RTX A4500", "RTX A4500"),
            ("NVIDIA RTX A4000", "RTX A4000")
        ]

        for gpu_id, display_name in gpu_types:
            self.gpu_type_combo.addItem(display_name, gpu_id)


    def fetch_and_create_pod(self):
        url = self.url_input.text()
        hf_token = self.hf_token_input.text()
        runpod_token = self.runpod_token_input.text()
        selected_gpu = self.gpu_type_combo.currentData()  # Get the selected GPU ID from the combo box

        if not hf_token or not runpod_token:
            self.output_display.setText("Please enter both HF and RunPod tokens.")
            return

        try:
            docker_commands = get_docker_commands(url)
            if docker_commands:
                env = {
                    'HF_TOKEN': hf_token,
                    'RUNPOD_TOKEN': runpod_token
                }
                pod = create_pod(
                    name=url.split('/')[-1],
                    image_name=docker_commands['docker_run_command'].split(' ')[-1],
                    gpu_type_id=selected_gpu,  # Use the selected GPU ID
                    cloud_type="SECURE",
                    gpu_count=1,
                    volume_in_gb=0,
                    container_disk_in_gb=200,
                    env=env
                )
                if pod and 'id' in pod:  # Check if pod creation was successful and contains 'id'
                    self.pod_url = f"https://{pod['id']}-5000.proxy.runpod.net"  # Set the pod URL using the pod ID
                    self.output_display.setText(f"Pod created successfully with ID: {pod['id']}\nAPI URL: {self.pod_url}")
                else:
                    self.output_display.setText("Pod creation failed, please check your inputs and try again.")
            else:
                self.output_display.setText("Failed to fetch Docker commands.")
        except Exception as e:
            self.output_display.setText(f"Error creating pod: {str(e)}")


    def send_custom_request(self):
        json_input = self.json_editor.toPlainText()
        try:
            parsed_json = json.loads(json_input)
            response = requests.post(self.pod_url + '/predictions', json=parsed_json)
            response_data = response.json()
            self.output_display.setText(f"Response:\n{json.dumps(response_data, indent=4)}")
            if 'output' in response_data and response_data['output'].startswith('data:image/png;base64,'):
                image_data = response_data['output'].split(',', 1)[1]
                image = base64.b64decode(image_data)
                pixmap = QPixmap()
                pixmap.loadFromData(image)
                self.current_pixmap = pixmap  # Set the current pixmap
                self.image_label.setPixmap(pixmap.scaled(400, 400, Qt.KeepAspectRatio))
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Invalid JSON", f"JSON Error: {str(e)}")
        except Exception as e:
            self.output_display.setText(f"Error sending request: {str(e)}")
    def save_image(self, event):
        # Only save if the pixmap is not None
        if self.current_pixmap:
            options = QFileDialog.Options()
            fileName, _ = QFileDialog.getSaveFileName(self, "Save Image", "",
                                                    "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)",
                                                    options=options)
            if fileName:
                self.current_pixmap.save(fileName)
        else:
            QMessageBox.warning(self, "Save Image", "No image to save.")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MainApp()
    ex.show()
    sys.exit(app.exec_())
