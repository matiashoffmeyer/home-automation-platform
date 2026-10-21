ARG BUILD_FROM
FROM ${BUILD_FROM}

# py3-opencv brings numpy with it and carries both FaceDetectorYN and an ONNX
# runner in cv2.dnn, so the gaze detector needs no pip wheels — onnxruntime has
# no musl build, and that is what ruled it out.
RUN apk add --no-cache ffmpeg python3 py3-opencv

# The weights are fetched rather than committed: a rebuild already needs the
# network for the base image, and 5 MB of binaries do not belong in the config
# repo. The checksums are what make downloading them safe to trust — they are
# the exact files the 24-degree threshold was measured on. The palm model is
# byte-identical to the palm_detection_full.tflite inside the mediapipe 0.10.14
# wheel the hand add-on pins — the gate must see what the add-on sees.
RUN mkdir -p /models \
    && wget -q -O /models/yunet.onnx \
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
    && wget -q -O /models/mobileone_s0_gaze.onnx \
        "https://github.com/yakhyo/gaze-estimation/releases/download/weights/mobileone_s0_gaze.onnx" \
    && wget -q -O /models/palm_detection_full.tflite \
        "https://storage.googleapis.com/mediapipe-assets/palm_detection_full.tflite" \
    && echo "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4  /models/yunet.onnx" | sha256sum -c - \
    && echo "8b4fdc4e3da44733c9a82e7776b411e4a39f94e8e285aee0fc85a548a55f7d9f  /models/mobileone_s0_gaze.onnx" | sha256sum -c - \
    && echo "1b14e9422c6ad006cde6581a46c8b90dd573c07ab7f3934b5589e7cea3f89a54  /models/palm_detection_full.tflite" | sha256sum -c -

COPY run.sh shim.py /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
