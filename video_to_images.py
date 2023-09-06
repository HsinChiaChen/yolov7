import cv2
import os

def video2imgs(videoPath, imgPath):
    if not os.path.exists(imgPath):
        os.makedirs(imgPath)             # 目標文件夾不存在，則創建
    cap = cv2.VideoCapture(videoPath)    # 獲取影片
    judge = cap.isOpened()               # 判斷是否能打開成功
    print(judge)
    fps = cap.get(cv2.CAP_PROP_FPS)      # 幀率，視頻每秒展示多少張圖片
    print('fps:',fps)

    frames = 1                           # 用於統計所有幀數
    count = 1                            # 用於統計保存的圖片數量

    while(judge):
        flag, frame = cap.read()         # 讀取每一張圖片 flag表示是否讀取成功，frame是圖片
        if not flag:
            print(flag)
            print("Process finished!")
            break
        else:
            if frames % 30 == 0:         # 每隔10幀抽一張
                imgname = 'tree_' + str(count).rjust(3,'0') + ".jpg"
                newPath = imgPath + imgname
                print(imgname)
                cv2.imwrite(newPath, frame, [cv2.IMWRITE_JPEG_QUALITY, 100])
                # cv2.imencode('.jpg', frame)[1].tofile(newPath)
                count += 1
        frames += 1
    cap.release()
    
video2imgs('/home/hcchen/yolov7/my_videos/farm.mp4','./images/')