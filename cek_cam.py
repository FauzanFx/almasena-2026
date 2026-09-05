import cv2

for i in range(3):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print(f"Kamera aktif dan berhasil dibaca pada Indeks: {i}")
            cv2.imshow(f"Test Kamera Indeks {i}", frame)
            cv2.waitKey(2000) # Tampilkan selama 2 detik
            cv2.destroyAllWindows()
        cap.release()