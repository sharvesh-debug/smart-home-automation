import time
import cv2
import os
import threading
import queue
from threading import Lock
from imutils.video import VideoStream
import requests
import logging
import datetime
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('Camera')

# Google Drive API configuration
FOLDER_ID = "1Yttia50DtyQFIKCfyX_cWADxlD4SEGU7"  # Target folder ID
TOKEN_FILE = "google_drive_token.json"
CREDENTIALS_FILE = "credentials.json"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

IMUTILS_AVAILABLE = True
CHUNK_DURATION = 10  # Duration in seconds for each video chunk

class Camera:
    def __init__(self, src=0, record_to_cloud=True):
        """
        Initializes and starts the camera stream with recording capability.
        src=0 is typically the built-in or first USB webcam.
        """
        print("INFO: Initializing camera stream...")
        self.src = src
        self.frame_lock = Lock()
        self.recording_lock = Lock()
        self.current_frame = None
        self.stream = None
        self.cap = None
        self.recording = False
        self.record_to_cloud = record_to_cloud
        self.video_writer = None
        self.recording_thread = None
        self.upload_queue = queue.Queue()
        self.upload_thread = None
        self.server_start_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_filename = ""
        self.frame_size = None
        self.drive_service = None
        self.stopping = False
        self.chunk_counter = 0  # Counter for chunk naming
        
        # Initialize Google Drive service
        self._init_drive_service()
        
        if IMUTILS_AVAILABLE:
            self._init_imutils_stream()
        else:
            self._init_cv2_stream()
            
        # Allow the camera sensor to warm up
        time.sleep(2.0)
        
        # Check if the camera started successfully
        test_frame = self.get_frame()
        if test_frame is None:
            print("FATAL ERROR: Camera could not be started. Check connection and permissions.")
            self.stop()
            raise IOError("Cannot open webcam")
            
        print("SUCCESS: Camera stream started successfully.")
        
        # Start recording immediately
        self.start_recording()
        
        # Start upload thread if needed
        if self.record_to_cloud and self.drive_service:
            self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
            self.upload_thread.start()
            logger.info("Upload thread started")
        else:
            logger.warning("Cloud recording disabled or Drive service not available - videos will be saved locally only")

    def _init_drive_service(self):
        """Initialize Google Drive service with proper authentication"""
        creds = None
        
        # Load existing token
        if os.path.exists(TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                logger.info("Loaded existing credentials from token file")
            except Exception as e:
                logger.error(f"Error loading credentials: {e}")
                creds = None
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    logger.info("Refreshing expired credentials...")
                    creds.refresh(Request())
                    logger.info("Credentials refreshed successfully")
                except Exception as e:
                    logger.error(f"Error refreshing credentials: {e}")
                    creds = None
            
            if not creds:
                if os.path.exists(CREDENTIALS_FILE):
                    try:
                        logger.info("Starting OAuth flow for new credentials...")
                        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                        creds = flow.run_local_server(port=0)
                        logger.info("OAuth flow completed successfully")
                    except Exception as e:
                        logger.error(f"Error during OAuth flow: {e}")
                        self._create_credentials_instructions()
                        return
                else:
                    logger.error("Credentials file not found")
                    self._create_credentials_instructions()
                    return
        
        # Save the credentials for the next run
        if creds:
            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                logger.info("Credentials saved to token file")
                
                # Build the Drive service
                self.drive_service = build('drive', 'v3', credentials=creds)
                logger.info("Google Drive service initialized successfully")
                
                # Test the service with a simple API call
                results = self.drive_service.files().list(pageSize=1).execute()
                logger.info("Google Drive API connection verified")
                
            except Exception as e:
                logger.error(f"Error initializing Drive service: {e}")
                self.drive_service = None
        else:
            logger.error("Failed to obtain valid credentials")
            self.drive_service = None

    def _create_credentials_instructions(self):
        """Create instructions for setting up credentials"""
        logger.error("""
    ====================================================================
    Google Drive Setup Required
    ====================================================================
    To enable cloud upload functionality:
    
    1. Go to Google Cloud Console: https://console.cloud.google.com/
    2. Create a new project or select existing project
    3. Enable Google Drive API:
       - Go to "APIs & Services" > "Library"
       - Search for "Google Drive API"
       - Click "Enable"
    4. Create credentials:
       - Go to "APIs & Services" > "Credentials"
       - Click "Create Credentials" > "OAuth client ID"
       - Choose "Desktop application"
       - Download the JSON file
    5. Rename the downloaded file to 'credentials.json'
    6. Place it in the same directory as this script
    7. Run this script again - it will open a browser for authorization
    
    For now, videos will be saved locally only.
    ====================================================================
    """)

    def _init_imutils_stream(self):
        """Initialize camera using imutils VideoStream"""
        try:
            self.stream = VideoStream(src=self.src).start()
            print("INFO: Using imutils VideoStream")
        except Exception as e:
            print(f"ERROR: Could not initialize imutils stream: {e}")
            print("INFO: Falling back to cv2.VideoCapture")
            self.stream = None
            self._init_cv2_stream()

    def _init_cv2_stream(self):
        """Initialize camera using cv2.VideoCapture"""
        self.cap = cv2.VideoCapture(self.src)
        if not self.cap.isOpened():
            raise IOError("Could not open camera")
            
        # Set camera properties for better performance
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        print("INFO: Using cv2.VideoCapture")
        
    def start_recording(self):
        """Start video recording session"""
        with self.recording_lock:
            if self.recording:
                logger.warning("Recording already started")
                return
                
            self.recording = True
            logger.info(f"Starting recording in {CHUNK_DURATION}-second chunks")
            
            # Start recording thread
            self.recording_thread = threading.Thread(target=self._recording_worker, daemon=True)
            self.recording_thread.start()
            logger.info("Recording thread started")

    def _recording_worker(self):
        """Worker thread for video recording in chunks"""
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        
        while self.recording:
            # Create new chunk filename
            self.chunk_counter += 1
            chunk_filename = f"recording_{self.server_start_time}_chunk_{self.chunk_counter:04d}.avi"
            
            logger.info(f"Starting new chunk: {chunk_filename}")
            
            # Initialize video writer for this chunk
            video_writer = None
            chunk_start_time = time.time()
            
            while self.recording and (time.time() - chunk_start_time) < CHUNK_DURATION:
                frame = self.get_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue
                    
                # Initialize video writer on first frame of chunk
                if video_writer is None:
                    self.frame_size = (frame.shape[1], frame.shape[0])
                    video_writer = cv2.VideoWriter(
                        chunk_filename,
                        fourcc,
                        20.0,
                        self.frame_size
                    )
                    logger.info(f"Video writer initialized for chunk: {chunk_filename}")
                
                # Write frame to video file
                video_writer.write(frame)
                time.sleep(0.05)  # Maintain ~20 FPS
                
            # Cleanup this chunk
            if video_writer is not None:
                video_writer.release()
                logger.info(f"Chunk completed: {chunk_filename}")
                
                # Check if file was actually created
                if os.path.exists(chunk_filename) and os.path.getsize(chunk_filename) > 0:
                    logger.info(f"Chunk saved locally: {chunk_filename} ({os.path.getsize(chunk_filename)} bytes)")
                    
                    # Queue for cloud upload if enabled
                    if self.record_to_cloud and self.drive_service and not self.stopping:
                        self.upload_queue.put(chunk_filename)
                        logger.info(f"Queued for upload: {chunk_filename}")
                    else:
                        if self.stopping:
                            logger.info("Stopping - chunk not queued for upload")
                        else:
                            logger.info("Local recording saved, cloud upload skipped (disabled or no Drive service)")
                else:
                    logger.error(f"Chunk file was not created properly: {chunk_filename}")
            
            # Small delay before starting next chunk if still recording
            if self.recording:
                time.sleep(0.1)

    def _upload_worker(self):
        """Worker thread for cloud uploads"""
        logger.info("Upload worker started")
        while not self.stopping:
            try:
                # Use a timeout to allow checking the stopping flag
                filename = self.upload_queue.get(timeout=1.0)
                if filename is None or self.stopping:
                    break
                    
                if not os.path.exists(filename):
                    logger.error(f"File not found: {filename}")
                    continue
                    
                upload_success = False
                try:
                    logger.info(f"Starting upload: {filename}")
                    upload_success = self._upload_to_drive(filename)
                    if upload_success:
                        # Only remove local file if upload was successful
                        try:
                            os.remove(filename)
                            logger.info(f"Successfully uploaded and removed local file: {filename}")
                        except OSError as e:
                            logger.error(f"Failed to delete local file {filename}: {e}")
                    else:
                        logger.error(f"Upload failed, keeping local file: {filename}")
                except Exception as e:
                    logger.error(f"Upload failed: {str(e)}")
                    logger.info(f"Keeping local file due to upload failure: {filename}")
                    
                    # Requeue for retry unless we're stopping
                    if not self.stopping:
                        self.upload_queue.put(filename)
                        logger.info(f"Re-queued for retry: {filename}")
                        time.sleep(5)
                    else:
                        logger.warning("Upload aborted due to shutdown")
                finally:
                    self.upload_queue.task_done()
            except queue.Empty:
                continue  # Timeout is normal, just check stopping flag again

    def _upload_to_drive(self, filename):
        """Upload file to Google Drive using proper API client"""
        if not self.drive_service:
            logger.warning("Cannot upload to Drive: Drive service not initialized")
            return False
            
        try:
            file_metadata = {
                'name': os.path.basename(filename),
                'parents': [FOLDER_ID]
            }
            
            media = MediaFileUpload(
                filename, 
                mimetype='video/avi',
                resumable=True,
                chunksize=1024*1024  # 1MB chunks for better reliability
            )
            
            logger.info(f"Uploading {filename} to Google Drive...")
            
            request = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            )
            
            file_info = None
            while file_info is None:
                status, file_info = request.next_chunk()
                if status:
                    logger.info(f"Upload progress: {int(status.progress() * 100)}%")
            
            if file_info:
                file_id = file_info.get('id')
                logger.info(f"Successfully uploaded to Drive: {filename} (File ID: {file_id})")
                return True
            else:
                logger.error("Upload completed but no file info received")
                return False
                
        except Exception as e:
            logger.error(f"Error during Drive upload: {str(e)}")
            return False

    def get_frame(self):
        """Returns the latest frame from the camera stream."""
        frame = None
        
        if self.stream is not None:
            frame = self.stream.read()
        elif self.cap is not None:
            ret, frame = self.cap.read()
            if not ret:
                logger.warning("Could not read frame from camera")
                return None
        
        # Store current frame for consistency
        if frame is not None:
            with self.frame_lock:
                self.current_frame = frame.copy()
                
        return frame
    
    def stop(self):
        """Stops the camera stream and recording."""
        self.stopping = True
        logger.info("Stopping camera stream...")
    
        # Stop recording first
        with self.recording_lock:
            if self.recording:
                self.recording = False
                logger.info("Recording flag set to False")
        
        # Wait for recording thread to finish
            if self.recording_thread is not None:
                self.recording_thread.join(timeout=5.0)
                if self.recording_thread.is_alive():
                    logger.warning("Recording thread did not terminate")
                else:
                    logger.info("Recording thread stopped")
    
        # Handle upload completion properly
        if self.upload_thread is not None:
            logger.info("Waiting for upload thread to finish current uploads...")
        
            # Give upload thread time to process any items that were just queued
            while not self.upload_queue.empty():
                logger.info(f"Waiting for {self.upload_queue.qsize()} upload(s) to complete...")
                time.sleep(1)  # Give upload thread time to pick up queued items
                try:
                    self.upload_queue.join()  # Wait for all items to be processed
                    break
                except Exception as e:
                    logger.error(f"Error waiting for uploads: {e}")
                    break
        
            # Now signal thread to exit
            logger.info("Signaling upload thread to exit")
            self.upload_queue.put(None)
            self.upload_thread.join()
            logger.info("Upload thread stopped")
    
        # Stop camera stream
        try:
            if self.stream is not None:
                self.stream.stop()
                logger.info("imutils VideoStream stopped")
        
            if self.cap is not None:
                self.cap.release()
                logger.info("cv2.VideoCapture released")
            
        except Exception as e:
            logger.error(f"Could not properly stop camera: {e}")
    
        logger.info("Camera stream stopped")
        
    def is_available(self):
        """Check if camera is available and working"""
        try:
            frame = self.get_frame()
            return frame is not None
        except Exception:
            return False

    def __del__(self):
        """Cleanup when object is destroyed"""
        try:
            self.stop()
        except:
            # Silently handle any errors during cleanup to prevent NameError during shutdown
            pass
