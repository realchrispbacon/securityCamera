'''
What: face_recognition.py is the main script that grabs frames from
 		thepi camera, detects faces, and loops through the encodings created 
		from running encode_faces.py which are used to detect faces and grant 
		authorization. If a face is detected and mqtt message is published to 
		a secure mqtt broker topic. If and unknown face is detected a mqtt 
		message is published to a secure mqtt broker topic and an email is sent
		containing an attached image of the unknown indivual as a notification 
		of the attempted access.
Who: Chris Punt and Nate Herder
When: 04/29/2020
Why: CS 300 Calvin University

Sources: https://www.pyimagesearch.com/2018/06/25/raspberry-pi-face-recognition/
USAGE: python pi_face_recognition.py --cascade haarcascade_frontalface_default.xml 
			--encodings encodings.pickle
'''

from imutils.video import VideoStream
from imutils.video import FPS
import paho.mqtt.client as mqtt
import face_recognition
import argparse
import imutils
import pickle
import time
import cv2
import send_emails
import os

# Constants
try:
    PASSWORD = os.getenv('CALVIN_MQTT_PASSWORD')
except:
    print('No environment varialble set for CALVIN_MQTT_PASSWORD')
    exit(1)
BROKER = 'iot.cs.calvin.edu'
USERNAME = "cs300" # Put broker username here
TOPIC = 'chrisNate/lock'
CERTS = '/etc/ssl/certs/ca-certificates.crt'
PORT = 8883
QOS = 0
OUTPUT_FILE = "/home/pi/securityCamera/output.jpg"
EMAIL = "sc300CU@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
CAMERA_SETUP_DELAY = 2.0
FRAME_DELAY = 2.0

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-c", "--cascade", default="/home/pi/securityCamera/haarcascade_frontalface_default.xml",
	help = "path to where the face cascade resides")
ap.add_argument("-e", "--encodings", default="/home/pi/securityCamera/encodings.pickle",
	help="path to serialized db of facial encodings")
args = vars(ap.parse_args())


# Callback when a message is published
def on_publish(client, userdata, mid):
    print("MQTT data published")

# Callback when connecting to the MQTT broker
def on_connect(client, userdata, flags, rc):
    if rc==0:
        print('Connected to',BROKER)
    else:
        print('Connection to',BROKER,'failed. Return code=',rc)
        exit(1)

# Setup MQTT client and callbacks
client = mqtt.Client()
client.username_pw_set(USERNAME, password=PASSWORD)
client.tls_set(CERTS)
client.on_connect = on_connect
client.on_publish = on_publish
# Connect to MQTT broker
client.connect(BROKER, PORT, 60)
client.loop_start()


# load the known faces and embeddings along with OpenCV's Haar
# cascade for face detection
print("[INFO] loading encodings + face detector...")
data = pickle.loads(open(args["encodings"], "rb").read())
detector = cv2.CascadeClassifier(args["cascade"])

# initialize the video stream and allow the camera sensor to warm up
print("[INFO] starting video stream...")
# vs = VideoStream(src=0).start()
vs = VideoStream(usePiCamera=True).start()
time.sleep(CAMERA_SETUP_DELAY)


# loop over frames from the video file stream
while True:
	faceDetected = False
	faceRecognized = False

	# grab the frame from the threaded video stream and resize it
	# to 500px (to speedup processing)
	frame = vs.read()
	frame = imutils.resize(frame, width=500)
	
	# convert the input frame from (1) BGR to grayscale (for face
	# detection) and (2) from BGR to RGB (for face recognition)
	gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
	rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

	# detect faces in the grayscale frame
	rects = detector.detectMultiScale(gray, scaleFactor=1.1, 
		minNeighbors=5, minSize=(30, 30), flags=cv2.CASCADE_SCALE_IMAGE)

	# OpenCV returns bounding box coordinates in (x, y, w, h) order
	# but we need them in (top, right, bottom, left) order, so we
	# need to do a bit of reordering
	boxes = [(y, x + w, y + h, x) for (x, y, w, h) in rects]

	# compute the facial embeddings for each face bounding box
	encodings = face_recognition.face_encodings(rgb, boxes)
	names = []

	# if any faces are detected, set faceDetected to True
	if (len(encodings) > 0):
		faceDetected = True

	# loop over the facial embeddings
	for encoding in encodings:
		# attempt to match each face in the input image to our known
		# encodings
		matches = face_recognition.compare_faces(data["encodings"],
			encoding)
		name = "Unknown"

		# check to see if we have found a match
		if True in matches:
			# find the indexes of all matched faces then initialize a
			# dictionary to count the total number of times each face
			# was matched
			matchedIdxs = [i for (i, b) in enumerate(matches) if b]
			counts = {}

			# loop over the matched indexes and maintain a count for
			# each recognized face face
			for i in matchedIdxs:
				name = data["names"][i]
				counts[name] = counts.get(name, 0) + 1

			# determine the recognized face with the largest number
			# of votes (note: in the event of an unlikely tie Python
			# will select first entry in the dictionary)
			name = max(counts, key=counts.get)

			# if there is a face recognized set faceRecognized to True
			if (name != "Unknown"):
				faceRecognized = True
		
		# update the list of names
		names.append(name)

	# loop over the recognized faces
	for ((top, right, bottom, left), name) in zip(boxes, names):
		# draw the predicted face name on the image
		cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
		y = top - 15 if top - 15 > 15 else top + 15
		cv2.putText(frame, name, (left, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75,
			(0, 255, 0), 2)

	if faceDetected:
		print("writing the image to file")
		cv2.imwrite(OUTPUT_FILE, frame)
		if faceRecognized:
			print("face was recognized")
			#publish to mqtt broker
			client.publish(TOPIC, 1)
		else:
			client.publish(TOPIC, 0)
			print("sending email")
			#send an email to ourselves to notify Failed Authentication
			send_emails.sendEmail(EMAIL, EMAIL, "Failed Authentication Alert", 
				"", OUTPUT_FILE, SMTP_SERVER, SMTP_PORT)

	time.sleep(FRAME_DELAY)