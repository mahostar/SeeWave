import os
import sys
import tempfile
import shutil
import time
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QPushButton, QProgressBar, QLabel, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMimeData, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QPalette, QColor, QIcon, QPixmap
from PyQt6.QtSvgWidgets import QSvgWidget
import ffmpeg
import seewav

# Redirect stdout and stderr to prevent console requirements
# This allows us to use console=False in PyInstaller while maintaining functionality
class StreamRedirector:
    def __init__(self, filename=None):
        self.terminal = sys.stdout
        if filename:
            self.log_file = open(filename, "a", encoding="utf-8")
        else:
            self.log_file = None
    
    def write(self, message):
        if self.log_file:
            self.log_file.write(message)
            self.log_file.flush()
    
    def flush(self):
        if self.log_file:
            self.log_file.flush()

# Setup redirect before any other code runs
log_path = os.path.join(os.path.expanduser("~"), "Documents", "seewav_log.txt")
sys.stdout = StreamRedirector(log_path)
sys.stderr = StreamRedirector(log_path)

# Get absolute paths for resources
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(SCRIPT_DIR, 'logo.png')
SVG_PATH = os.path.join(SCRIPT_DIR, 'image.svg')

class AudioProcessingThread(QThread):
    progress = pyqtSignal(int)
    error = pyqtSignal(str)
    finished = pyqtSignal(str)
    frame_update = pyqtSignal(int, int, float)  # current frame, total frames, time left
    status_update = pyqtSignal(str)  # For status messages

    def __init__(self, input_file, output_file):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.temp_dir = None
        self.start_time = 0
        self.total_frames = 0
        self.current_frame = 0
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        try:
            self.start_time = time.time()
            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp()
            
            # Convert MP4 to MP3 if needed
            input_path = Path(self.input_file)
            if input_path.suffix.lower() == '.mp4':
                self.status_update.emit("Converting MP4 to MP3...")
                self.progress.emit(10)
                temp_mp3 = os.path.join(self.temp_dir, 'temp.mp3')
                try:
                    ffmpeg.input(str(input_path)).output(temp_mp3).run(overwrite_output=True)
                    self.input_file = temp_mp3
                except ffmpeg.Error as e:
                    self.error.emit(f"FFmpeg error: {str(e)}")
                    return

                if self.cancelled:
                    return
                    
            self.progress.emit(30)
            self.status_update.emit("Analyzing audio...")

            # Process with seewav
            try:
                # Create a progress callback function that emits signals
                def update_progress(value):
                    if value == 80:
                        self.status_update.emit("Creating final video...")
                    self.progress.emit(value)
                
                # Make sure all paths are Path objects
                input_file_path = Path(self.input_file)
                temp_dir_path = Path(self.temp_dir)
                output_file_path = Path(self.output_file)
                
                # Get audio duration to estimate total frames
                probe = ffmpeg.probe(str(input_file_path))
                duration = float(probe['format']['duration'])
                self.total_frames = int(duration * 60)  # 60 fps by default
                
                # Create a frame tracking function
                def frame_callback(frame_num, total_frames):
                    if self.cancelled:
                        raise InterruptedError("Processing cancelled by user")
                        
                    self.current_frame = frame_num
                    elapsed_time = time.time() - self.start_time
                    if frame_num > 0:
                        time_per_frame = elapsed_time / frame_num
                        frames_left = total_frames - frame_num
                        time_left = frames_left * time_per_frame
                    else:
                        time_left = 0
                    
                    self.frame_update.emit(frame_num, total_frames, time_left)
                
                self.status_update.emit("Generating frames...")
                seewav.visualize(
                    input_file_path,
                    temp_dir_path,
                    output_file_path,
                    rate=60,
                    bars=50,
                    fg_color=(1.0, 1.0, 1.0),  # Pure white color for waves
                    fg_opacity=1.0,  # Full opacity
                    bg_color=(0.0, 0.2, 0.9),  # More vibrant blue background
                    size=(1920, 1080),  # Full HD
                    progress_callback=update_progress,
                    frame_callback=frame_callback
                )
                self.progress.emit(100)
                self.finished.emit(self.output_file)
            except InterruptedError:
                self.status_update.emit("Processing cancelled")
                return
            except Exception as e:
                self.error.emit(f"SeeWave error: {str(e)}")

        except Exception as e:
            self.error.emit(str(e))
        finally:
            # Cleanup temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                except Exception as e:
                    print(f"Error cleaning up temp directory: {e}")

class DropArea(QWidget):
    fileDropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        layout = QVBoxLayout()
        self.label = QLabel("Drag & Drop\nMP3, MP4, or WAV file here\nor click to select")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.setLayout(layout)
        self.setStyleSheet("""
            QWidget {
                border: 2px dashed #4B89DC;
                border-radius: 10px;
                padding: 20px;
                background-color: #1F2937;
                color: #4B89DC;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.mp3', '.mp4', '.wav')):
                self.fileDropped.emit(file_path)
                break

    def mousePressEvent(self, event):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio/Video File",
            "",
            "Audio/Video Files (*.mp3 *.mp4 *.wav)"
        )
        if file_path:
            self.fileDropped.emit(file_path)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.processing_thread = None
        self.selected_input_file = None
        self.selected_output_file = None

    def initUI(self):
        self.setWindowTitle('SeeWave Generator')
        self.setMinimumSize(700, 550)  # Increased window size
        
        # Set app icon
        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))
        else:
            print(f"Warning: Logo file not found at {LOGO_PATH}")

        # Set dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #111827;
            }
            QLabel {
                color: #E5E7EB;
            }
            QPushButton {
                background-color: #4B89DC;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #5A98EB;
            }
            QPushButton:disabled {
                background-color: #2D3748;
                color: #9CA3AF;
            }
            QProgressBar {
                border: 2px solid #4B89DC;
                border-radius: 5px;
                text-align: center;
                color: black;
                height: 25px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #10B981;
                border-radius: 3px;
            }
        """)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Header with SVG image and title
        header_layout = QHBoxLayout()
        
        # SVG image - fix proportions
        if os.path.exists(SVG_PATH):
            svg_widget = QSvgWidget(SVG_PATH)
            svg_widget.setFixedSize(QSize(350, 120))  # Rectangular size to match the actual image ratio
            header_layout.addWidget(svg_widget, 0, Qt.AlignmentFlag.AlignVCenter)
            header_layout.addSpacing(10)  # Add some spacing between image and text
        else:
            print(f"Warning: SVG file not found at {SVG_PATH}")
        
        # App title and description
        title_layout = QVBoxLayout()
        title_label = QLabel("SeeWave: Waveform Generator")
        title_label.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")  # Larger font
        subtitle_label = QLabel("Create waveform visualizations")
        subtitle_label.setStyleSheet("font-size: 14px; color: #A3B1CC;")
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        layout.addSpacing(30)  # More spacing

        # Drop area
        self.drop_area = DropArea()
        self.drop_area.fileDropped.connect(self.on_file_selected)
        layout.addWidget(self.drop_area)
        
        # File selection info
        self.file_info_label = QLabel("")
        self.file_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_info_label.setStyleSheet("color: #10B981; margin-top: 10px;")
        layout.addWidget(self.file_info_label)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        # Select output location button
        self.output_location_btn = QPushButton("Select Output Location")
        self.output_location_btn.clicked.connect(self.select_output_location)
        button_layout.addWidget(self.output_location_btn)
        
        # Start button
        self.start_btn = QPushButton("Start Processing")
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
            }
            QPushButton:hover {
                background-color: #0D9B6D;
            }
            QPushButton:disabled {
                background-color: #2D3748;
                color: #9CA3AF;
            }
        """)
        button_layout.addWidget(self.start_btn)
        
        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
            QPushButton:disabled {
                background-color: #2D3748;
                color: #9CA3AF;
            }
        """)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Set initial button states
        self.output_location_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Pro tip with yellow background
        pro_tip_container = QWidget()
        pro_tip_container.setFixedHeight(100)  # Control the exact height
        pro_tip_container.setFixedWidth(720)  # Control the exact width
        pro_tip_container.setStyleSheet("background-color: rgba(255, 230, 0, 0.2); border-radius: 10px; margin: 10px;")
        pro_tip_layout = QVBoxLayout(pro_tip_container)
        pro_tip_layout.setContentsMargins(10, 5, 10, 5)  # Minimal vertical padding
        pro_tip_label = QLabel("PRO TIP: For best results, use high quality audio files with minimal background noise")
        pro_tip_label.setStyleSheet("color: #FFFFFF; font-style: italic; font-weight: bold; padding: 0px; font-size: 16px;")  # Added font size
        pro_tip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pro_tip_layout.addWidget(pro_tip_label)
        
        # Add the pro tip container in a horizontal layout for width control
        pro_tip_horizontal = QHBoxLayout()
        pro_tip_horizontal.addStretch(1)  # Add stretching space on the left
        pro_tip_horizontal.addWidget(pro_tip_container, 6)  # Give the container a relative width of 6
        pro_tip_horizontal.addStretch(1)  # Add stretching space on the right
        layout.addLayout(pro_tip_horizontal)
        
        # Add some bottom spacing
        layout.addSpacing(10)

    def on_file_selected(self, file_path):
        self.selected_input_file = file_path
        file_name = os.path.basename(file_path)
        self.file_info_label.setText(f"Selected file: {file_name}")
        self.output_location_btn.setEnabled(True)
        
        # Auto-set a default output location in Documents folder
        documents_path = os.path.join(os.path.expanduser("~"), "Documents")
        file_base_name = os.path.splitext(file_name)[0]
        self.selected_output_file = os.path.join(documents_path, f"{file_base_name}_wave.mp4")
        
        # Enable the start button since we have both input and output
        self.start_btn.setEnabled(True)

    def select_output_location(self):
        if not self.selected_input_file:
            return
            
        # Get base filename
        input_filename = os.path.basename(self.selected_input_file)
        base_name = os.path.splitext(input_filename)[0]
        
        # Default to Documents folder
        documents_path = os.path.join(os.path.expanduser("~"), "Documents")
        default_path = os.path.join(documents_path, f"{base_name}_wave.mp4")
        
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Output Video",
            default_path,
            "Video Files (*.mp4)"
        )
        
        if output_path:
            self.selected_output_file = output_path
            self.start_btn.setEnabled(True)

    def start_processing(self):
        if not self.selected_input_file or not self.selected_output_file:
            return

        # Update UI for processing state
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.drop_area.setEnabled(False)
        self.output_location_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_label.setText("Initializing...")

        # Start processing thread
        self.processing_thread = AudioProcessingThread(self.selected_input_file, self.selected_output_file)
        self.processing_thread.progress.connect(self.update_progress)
        self.processing_thread.error.connect(self.handle_error)
        self.processing_thread.finished.connect(self.handle_completion)
        self.processing_thread.frame_update.connect(self.update_frame_status)
        self.processing_thread.status_update.connect(self.update_status)
        self.processing_thread.start()

    def cancel_processing(self):
        if self.processing_thread and self.processing_thread.isRunning():
            self.status_label.setText("Cancelling...")
            self.processing_thread.cancel()
            # Reset UI after a short delay
            QApplication.processEvents()
            self.reset_ui()

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        QApplication.processEvents()  # Force UI update
        
    def update_frame_status(self, current_frame, total_frames, time_left):
        minutes = int(time_left / 60)
        seconds = int(time_left % 60)
        self.status_label.setText(f"Processing {current_frame}/{total_frames} frames\nTime remaining: {minutes}m {seconds}s")
        QApplication.processEvents()  # Force UI update
        
    def update_status(self, status):
        self.status_label.setText(status)
        QApplication.processEvents()  # Force UI update

    def handle_error(self, error_msg):
        error_box = QMessageBox(self)
        error_box.setWindowTitle("Error")
        error_box.setIcon(QMessageBox.Icon.Critical)
        error_box.setText(error_msg)
        error_box.setStyleSheet("QLabel{color: black;}")
        error_box.exec()
        self.reset_ui()

    def handle_completion(self, output_path):
        self.status_label.setText("Processing complete!")
        success_msg = QMessageBox(self)
        success_msg.setWindowTitle("Success")
        success_msg.setIcon(QMessageBox.Icon.Information)
        success_msg.setText(f"Video saved to:\n{output_path}")
        success_msg.setStyleSheet("QLabel{color: black;}")
        success_msg.exec()
        self.reset_ui()

    def reset_ui(self):
        self.progress_bar.setVisible(False)
        self.drop_area.setEnabled(True)
        self.output_location_btn.setEnabled(self.selected_input_file is not None)
        self.start_btn.setEnabled(self.selected_input_file is not None and self.selected_output_file is not None)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("")

def main():
    try:
        app = QApplication(sys.argv)
        
        # Set application icon for all windows, taskbar, etc.
        if os.path.exists(LOGO_PATH):
            app_icon = QIcon(LOGO_PATH)
            app.setWindowIcon(app_icon)  # Set app icon for taskbar
        else:
            print(f"Warning: Logo file not found at {LOGO_PATH}")
            
        window = MainWindow()
        
        # Set window icon again for this specific window
        if os.path.exists(LOGO_PATH):
            window.setWindowIcon(QIcon(LOGO_PATH))
            
        # For Windows: explicitly set the application ID to ensure taskbar icon works
        try:
            import ctypes
            app_id = 'SeeWave.Generator.1.0'  # Arbitrary string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except:
            pass  # Silently ignore if this fails
            
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        # Log the exception
        log_error = f"Unhandled exception: {str(e)}\n"
        import traceback
        log_error += traceback.format_exc()
        
        # Write to log file
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_error)
        
        # Show error message to user
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            error_box = QMessageBox()
            error_box.setWindowTitle("Error")
            error_box.setIcon(QMessageBox.Icon.Critical)
            error_box.setText(f"An error occurred: {str(e)}\nCheck log file at {log_path}")
            error_box.setStyleSheet("QLabel{color: black;}")
            error_box.exec()
        except:
            pass  # If even the error dialog fails, just exit
        
        sys.exit(1)

if __name__ == '__main__':
    main() 