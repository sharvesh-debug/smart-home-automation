import face_recognition
import cv2
import pickle
import time
import os
import logging
import numpy as np
from threading import Lock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('security.log')
    ]
)
logger = logging.getLogger('SecuritySystem')

# Constants
KNOWN_FACES_FILE = "known_faces.pkl"  
ENTERED_FACE="acessed_persons.pkl"
COOLDOWN_SECONDS = 23  # Cooldown after known face detection
PERMISSION_REQUEST_TIMEOUT = 30 # Timeout for permission requests

class FaceRecognitionSecurity:
    def __init__(self, camera, permission_state, unlock_callback, notification_callback,security_action_callback=None):
        """
        Initialize the security system with:
        - camera: Camera object for frame capture
        - permission_state: Shared state for permission requests
        - unlock_callback: Function to call when unlocking door
        - notification_callback: Function to add notifications
        """
        self.camera = camera
        self.permission_state = permission_state
        self.unlock_callback = unlock_callback
        self.notification_callback = notification_callback
        self.security_action_callback=security_action_callback
        self.data_lock = Lock()
        self.known_face_encodings = []
        self.known_face_names = []
        self.last_known_face_time = {}
        self.last_unknown_face_time = 0
        self.last_detected_face = None  # Store face image in memory as JPEG bytes
        self.is_unlocking = False  # Track unlocking state
        self.last_unlock_time = 0  # Track last unlock time
        self.unlock_cooldown = 15  # Cooldown period in seconds after unlocking
        self.acessed_face_encodings = []
        self.acessed_face_names = []
        # Ensure directory exists for known faces file - Fixed logic
        faces_dir = os.path.dirname(KNOWN_FACES_FILE)
        if faces_dir:  # Only create directory if dirname is not empty
            os.makedirs(faces_dir, exist_ok=True)
        
        self.load_known_faces()
        logger.info("Security system initialized")

    def load_known_faces(self):
        """Load known faces from the pickle file"""
        
        if os.path.exists(KNOWN_FACES_FILE):
            try:
                with open(KNOWN_FACES_FILE, 'rb') as f:
                    
                    # Check if file is empty
                    if os.path.getsize(KNOWN_FACES_FILE) == 0:
                        logger.info("Known faces file found but is empty. Starting fresh")
                        self.known_face_encodings = []
                        self.known_face_names = []
                        # Create initial empty data structure
                        self._create_empty_faces_file()
                    else:
                        data = pickle.load(f)
                        self.known_face_encodings = data['encodings']
                        self.known_face_names = data['names']
                        print( self.known_face_names)
                        logger.info(f"Loaded {len(self.known_face_names)} known faces")
            except (pickle.PickleError, EOFError, KeyError) as e:
                logger.error(f"Error loading known faces file: {e}")
                logger.info("Creating new known faces file")
                self.known_face_encodings = []
                self.known_face_names = []
                self._create_empty_faces_file()
        else:
            logger.info("No known faces file found. Creating new file")
            self.known_face_encodings = []
            self.known_face_names = []
            self._create_empty_faces_file()
    def acessed_person_(self):
        """Load temperorily allowes faces from the pickle file"""
        
        if os.path.exists(ENTERED_FACE):
            try:
                with open(ENTERED_FACE, 'rb') as f:
                    
                    # Check if file is empty
                    if os.path.getsize(ENTERED_FACE) == 0:
                        logger.info("Known faces file found but is empty. Starting fresh")
                        self.acessed_person_encodings = []
                        self.acessed_person_names = []
                        # Create initial empty data structure
                        self._create_empty_faces_file_acessed()
                    else:
                        data = pickle.load(f)
                        self. acessed_person_encodings= data['encodings']
                        self.acessed_person_names= data['names']
                        print( self.acessed_person_names)
                        logger.info(f"Loaded {len(self.acessed_face_names)} known faces")
            except (pickle.PickleError, EOFError, KeyError) as e:
                logger.error(f"Error loading Entered faces file: {e}")
                logger.info("Creating new entered faces file")
                self. acessed_person_encodings= []
                self.acessed_person_names = []
                self._create_empty_faces_file_acessed()
        else:
            logger.info("No entered faces file found. Creating new file")
            self.acessed_face_encodings = []
            self.acessed_face_names = []
            self._create_empty_faces_file_acessed()
    
    def _create_empty_faces_file(self):
        """Create an empty known faces file with proper structure"""
        try:
            with open(KNOWN_FACES_FILE, 'wb') as f:
                pickle.dump({
                    'encodings': [],
                    'names': []
                }, f)
            logger.info("Created empty known faces file")
        except Exception as e:
            logger.error(f"Error creating known faces file: {e}")
        
    def _create_empty_faces_file_acessed(self):
        """Create an empty entered faces file with proper structure"""
        try:
            with open(ENTERED_FACE, 'wb') as f:
                pickle.dump({
                    'encodings': [],
                    'names': []
                }, f)
            logger.info("Created empty ENTERED faces file")
        except Exception as e:
            logger.error(f"Error creating entered faces file: {e}")
        

    def save_known_faces(self):
        """Save known faces to the pickle file"""
        
        with self.data_lock:
            with open(KNOWN_FACES_FILE, 'wb') as f:
                pickle.dump({
                    'encodings': self.known_face_encodings,
                    'names': self.known_face_names
                }, f)
            logger.info(f"Saved {len(self.known_face_names)} known faces")
        return True
        
    def save_known_faces_acessed(self):
        """Save acessed faces to the pickle file"""
        
        with self.data_lock:
            with open(ENTERED_FACE, 'wb') as f:
                pickle.dump({
                    'encodings': self.acessed_face_encodings,
                    'names': self.acessed_face_names
                }, f)
            logger.info(f"Saved {len(self.acessed_face_names)} known faces")
        return True

    def add_new_face(self, name, encoding_to_add=None):
        """
        Add a new face to the known faces database
        - name: Name to associate with the face
        - encoding_to_add: Optional face encoding (if not provided, uses last detected face)
        """
        
        with self.data_lock:
            if not self.last_detected_face:
                logger.error("No face image available to add")
                return False
            # Create a copy of the buffer to avoid corruption
            image_buffer = bytes(self.last_detected_face)

        nparr = np.frombuffer(image_buffer, np.uint8)
        face_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if face_image is None:
            logger.error("Failed to decode face image")
            return False
            
        # Convert to RGB (face_recognition uses RGB)
        rgb_face_image = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)
            
        # IMPROVED: Enhanced preprocessing for better angle handling
        # Apply histogram equalization for better lighting normalization
        lab = cv2.cvtColor(face_image, cv2.COLOR_BGR2LAB)
        lab[:,:,0] = cv2.equalizeHist(lab[:,:,0])
        enhanced_face = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        
        # Encode the face with enhanced preprocessing
        new_encodings = face_recognition.face_encodings(enhanced_face, model='large')
            
        if not new_encodings:
            # Fallback to original image if enhanced doesn't work
            new_encodings = face_recognition.face_encodings(rgb_face_image, model='large')
            
        if not new_encodings:
            logger.error("Could not extract face features from image")
            return False
                
        encoding_array = new_encodings[0]
            
        with self.data_lock:
            # Check if name already exists
            if name in self.known_face_names:
                logger.info(f"Updating existing user '{name}'")
                index = self.known_face_names.index(name)
                self.known_face_encodings[index] = encoding_array
            else:
                logger.info(f"Adding new user '{name}'")
                self.known_face_names.append(name)
                self.known_face_encodings.append(encoding_array)
                
        return self.save_known_faces()
    
    def add_new_face_acessed(self, name, encoding_to_add=None):
        """
        Add a new face to the entered faces database
        - name: Name to associate with the face
        - encoding_to_add: Optional face encoding (if not provided, uses last detected face)
        """
        
        with self.data_lock:
            if not self.last_detected_face:
                logger.error("No face image available to add")
                return False
            # Create a copy of the buffer to avoid corruption
            image_buffer = bytes(self.last_detected_face)

        nparr = np.frombuffer(image_buffer, np.uint8)
        face_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if face_image is None:
            logger.error("Failed to decode face image")
            return False
            
        # Convert to RGB (face_recognition uses RGB)
        rgb_face_image = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)
            
        # IMPROVED: Enhanced preprocessing for better angle handling
        # Apply histogram equalization for better lighting normalization
        lab = cv2.cvtColor(face_image, cv2.COLOR_BGR2LAB)
        lab[:,:,0] = cv2.equalizeHist(lab[:,:,0])
        enhanced_face = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        
        # Encode the face with enhanced preprocessing
        new_encodings = face_recognition.face_encodings(enhanced_face, model='large')
            
        if not new_encodings:
            # Fallback to original image if enhanced doesn't work
            new_encodings = face_recognition.face_encodings(rgb_face_image, model='large')
            
        if not new_encodings:
            logger.error("Could not extract face features from image")
            return False
                
        encoding_array = new_encodings[0]
            
        with self.data_lock:
            # Check if name already exists
            if name in self.acessed_face_names:
                logger.info(f"Updating existing user '{name}'")
                index = self.acessed_face_names.index(name)
                self.acessed_face_encodings[index] = encoding_array
            else:
                logger.info(f"Adding new user '{name}'")
                self.acessed_face_names.append(name)
                self.acessed_face_encodings.append(encoding_array)
                
        return self.save_known_faces_acessed()
       
                
        
   
    def unlock_with_cooldown(self):
        """Unlock door with proper cooldown management"""
        if self.is_unlocking:
            logger.warning("Unlock already in progress")
            return
            
        self.is_unlocking = True

        logger.info("Starting door unlock process")
        self.unlock_callback()
        logger.info("Door unlock completed")
        
       
        self.last_unlock_time = time.time()
        self.is_unlocking = False

    def process_frames(self):
        """Main processing loop for face detection and recognition"""
        logger.info("Starting security processing thread")
        
        if not self.camera:
            logger.error("No camera available for security processing")
            return 
            
        # Cooldown period to allow system to stabilize
        time.sleep(5)
            
        while True:
            
            # Skip processing if unlocking or in cooldown
            current_time = time.time()
            if self.is_unlocking or (current_time - self.last_unlock_time < self.unlock_cooldown):
                time.sleep(0.5)
                continue
                
            # Check if permission request has timed out
            with self.data_lock:
                if ('timestamp' in self.permission_state and 
                    current_time - self.permission_state['timestamp'] > PERMISSION_REQUEST_TIMEOUT):
                    logger.info("Permission request timed out")
                    self.permission_state.clear()
                
            # Get frame from camera
            frame = self.camera.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue
            
            # Skip processing if a permission request is already active
            if 'encoding' in self.permission_state:
                time.sleep(4)  # Sleep longer while waiting for user action
                continue

            # IMPROVED: Better frame resolution for accuracy and angle detection
            small_frame = cv2.resize(frame, (0, 0), fx=0.4, fy=0.4)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            # IMPROVED: Enhanced preprocessing for better angle invariance
            # Apply histogram equalization for better lighting conditions
            lab_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2LAB)
            lab_frame[:,:,0] = cv2.equalizeHist(lab_frame[:,:,0])
            enhanced_frame = cv2.cvtColor(lab_frame, cv2.COLOR_LAB2RGB)

            # IMPROVED: Use multiple detection methods for better angle coverage
            face_locations = face_recognition.face_locations(enhanced_frame, model='hog')
            if not face_locations:
                # Try with CNN model for better angle detection (slower but more accurate)
                face_locations = face_recognition.face_locations(rgb_small_frame, model='cnn')
            
            if not face_locations:
                time.sleep(0.2)
                continue
                    
            # IMPROVED: Use large model for better angle handling
            face_encodings = face_recognition.face_encodings(enhanced_frame, face_locations, model='large')
            if not face_encodings:
                # Fallback to original frame if enhanced doesn't work
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations, model='large')

            found_known_face = False
            for face_encoding in face_encodings:
                 with self.data_lock:
                    if self.known_face_encodings:
                        # IMPROVED: More tolerant thresholds for angle variations
                        face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            
                        # IMPROVED: Adjusted tolerances for better angle handling
                        strict_tolerance = 0.45   # More lenient for angle variations
                        normal_tolerance = 0.55   # Increased for different angles
                        loose_tolerance = 0.65    # Higher tolerance for challenging angles
            
                        # IMPROVED: Multi-stage matching for angle invariance
                        candidates = np.where(face_distances < normal_tolerance)[0]
                        
                        if len(candidates) > 0:
                            # Get the best match among candidates
                            candidate_distances = face_distances[candidates]
                            best_candidate_idx = candidates[np.argmin(candidate_distances)]
                            best_distance = face_distances[best_candidate_idx]
                            
                            # IMPROVED: Use multiple tolerance levels for compare_faces
                            strict_matches = face_recognition.compare_faces(
                                self.known_face_encodings, 
                                face_encoding, 
                                tolerance=strict_tolerance
                            )
                            normal_matches = face_recognition.compare_faces(
                                self.known_face_encodings, 
                                face_encoding, 
                                tolerance=normal_tolerance
                            )
                            loose_matches = face_recognition.compare_faces(
                                self.known_face_encodings, 
                                face_encoding, 
                                tolerance=loose_tolerance
                            )
                            
                            # Combine all matches for comprehensive checking
                            matches = [strict_matches[i] or normal_matches[i] or loose_matches[i] 
                                     for i in range(len(self.known_face_encodings))]
                        else:
                            best_distance = float('inf')
                            best_candidate_idx = -1
                            matches = []
                    else:
                        matches = []
                        face_distances = []
                        best_distance = float('inf')
                        best_candidate_idx = -1
               
                   
            name = "Unknown"
            # IMPROVED: Enhanced matching logic for angle tolerance
            if self.known_face_encodings and best_distance < loose_tolerance:
                if best_distance < strict_tolerance:
                    confidence_level = "high"
                elif best_distance < normal_tolerance:
                    confidence_level = "medium"
                else:
                    confidence_level = "low"
            
                # IMPROVED: More permissive acceptance for angle variations
                if confidence_level in ["high", "medium", "low"]:
                   
                    with self.data_lock:
                        name = self.known_face_names[best_candidate_idx]
            
                        logger.info(f"Face matched: {name} (distance: {best_distance:.3f}, confidence: {confidence_level})")
            
                        if current_time - self.last_known_face_time.get(name, 0) > COOLDOWN_SECONDS:
                       
                            logger.info(f"Recognized face: {name}. Unlocking door.")
                            self.unlock_with_cooldown()
                            self.notification_callback(
                    "fa-door-open", 
                    "success", 
                    f"{name} entered (confidence: {confidence_level}).", 
                    "/security"
                            )
                            self.last_known_face_time[name] = current_time
                            found_known_face = True
                            break
                            
            # IMPROVED: Enhanced fallback matching for angle variations
            if not found_known_face and self.known_face_encodings:
                if True in matches:
                    first_match_index = matches.index(True)
                    with self.data_lock:
                        name = self.known_face_names[first_match_index]
                        match_distance = face_distances[first_match_index] if len(face_distances) > first_match_index else 0
                        
                        if current_time - self.last_known_face_time.get(name, 0) > COOLDOWN_SECONDS:
                            logger.info(f"Recognized face (angle-tolerant): {name} (distance: {match_distance:.3f}). Unlocking door.")
                            self.unlock_with_cooldown()
                            self.notification_callback(
                            "fa-door-open", 
                            "success", 
                            f"{name} entered (angle-tolerant match).", 
                            "/security"
                            )
                            self.last_known_face_time[name] = current_time
                            found_known_face = True
                            break

            # Handle unknown faces
            if not found_known_face and face_encodings:
               
                if current_time - self.last_unknown_face_time > COOLDOWN_SECONDS:
                    logger.info("Unknown face detected. Requesting permission.")
        
                    # Extract face from original frame (scale back up)
                    top, right, bottom, left = face_locations[0]
                    top = int(top * 2.5)  # Adjusted scaling for 0.4 resize
                    right = int(right * 2.5)
                    bottom = int(bottom * 2.5)
                    left = int(left * 2.5)
            
                    # Add padding
                    pad = 20
                    height, width = frame.shape[:2]
                    top = max(0, top - pad)
                    left = max(0, left - pad)
                    bottom = min(height, bottom + pad)
                    right = min(width, right + pad)
            
                    # Extract face region
                    face_image = frame[top:bottom, left:right]
                    
            
                    if face_image.size > 0:
                        # FIXED CODE: Create a copy to avoid memory corruption
                        ret, jpeg_encoded = cv2.imencode('.jpg', face_image.copy())
                        if ret:
                            # Create a copy to avoid memory corruption
                            jpeg_bytes = jpeg_encoded.tobytes()
                            with self.data_lock:
                                self.last_detected_face = jpeg_bytes
                            # Explicitly delete the encoded array
                            del jpeg_encoded
                    
                            # FIXED: Use proper thread-safe permission state
                            with self.data_lock:
                                self.permission_state['encoding'] = face_encodings[0].tolist()
                                self.permission_state['timestamp'] = current_time
                                self.permission_state['active'] = True  # Add active flag
                    
                            # FIXED: Update global permission state properly
                                global permission_request_state
                                self.permission_state.update({
                        'encoding': face_encodings[0].tolist(),
                        'timestamp': current_time,
                        'active': True,
                        'face_image_available': True
                    })
        
            # Send notification AFTER setting up the state
            self.notification_callback(
                "fa-user-secret", 
            "warning", 
            "Unknown person detected at the door.", 
            "/security"
            )
        
            self.last_unknown_face_time = current_time
        
        # FIXED: Call security action callback AFTER everything is set up
            if self.security_action_callback:
                self.security_action_callback()
        
        # Clean up frame references to prevent memory leaks
        del frame, small_frame, rgb_small_frame
        if 'face_image' in locals():
            del face_image
        if 'enhanced_frame' in locals():
            del enhanced_frame
        if 'lab_frame' in locals():
            del lab_frame
        
        self.save_known_faces()
        time.sleep(0.2)
