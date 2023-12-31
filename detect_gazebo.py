import argparse
import time
from pathlib import Path

import cv2
import torch
import torch.backends.cudnn as cudnn
import numpy as np
from numpy import random

from models.experimental import attempt_load
from utils.datasets import LoadStreams, LoadImages
from utils.general import check_img_size, check_requirements, check_imshow, non_max_suppression, apply_classifier, \
    scale_coords, xyxy2xywh, strip_optimizer, set_logging, increment_path
from utils.my_plots import plot_one_box, plot_one_box_no_text, mask, min_max_filtering, point_store, draw_line
from utils.torch_utils import select_device, load_classifier, time_synchronized, TracedModel

import tf
import rospy
from my_vision import RobotSensor_vision
from cv_bridge import CvBridge, CvBridgeError
from geometry_msgs.msg import Twist
Vision = RobotSensor_vision()
bridge = CvBridge()

def detect(save_img=False):
    source, weights, view_img, save_txt, imgsz, trace = opt.source, opt.weights, opt.view_img, opt.save_txt, opt.img_size, not opt.no_trace
    rate = rospy.Rate(100)
    # Directories
    save_dir = Path(increment_path(Path(opt.project) / opt.name, exist_ok=opt.exist_ok))  # increment run
    (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    # Initialize
    set_logging()
    device = select_device(opt.device)
    half = device.type != 'cpu'  # half precision only supported on CUDA

    # Load model
    model = attempt_load(weights, map_location=device)  # load FP32 model
    stride = int(model.stride.max())  # model stride
    imgsz = check_img_size(imgsz, s=stride)  # check img_size

    if trace:
        model = TracedModel(model, device, opt.img_size)

    if half:
        model.half()  # to FP16

    # # Second-stage classifier
    # classify = False
    # if classify:
    #     modelc = load_classifier(name='resnet101', n=2)  # initialize
    #     modelc.load_state_dict(torch.load('weights/resnet101.pt', map_location=device)['model']).to(device).eval()

    # Get names and colors
    names = model.module.names if hasattr(model, 'module') else model.names
    colors = [[random.randint(0, 255) for _ in range(3)] for _ in names]

    # Run inference
    if device.type != 'cpu':
        model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(next(model.parameters())))  # run once
    old_img_w = old_img_h = imgsz
    old_img_b = 1
    
    # # 設定相機配置
    # config = rs.config()
    # config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    # config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    # # 管理相機的資源和執行資料串流
    # pipeline = rs.pipeline()
    # profile = pipeline.start(config)

    # # 設定深度影像對齊
    # align_to = rs.stream.color
    # align = rs.align(align_to)

    prev_frame_time = 0
    # while(True):
    while not rospy.is_shutdown():
        # t0 = time.time()
        new_frame_time = time.time()
        fps = 1/(new_frame_time-prev_frame_time)
        prev_frame_time = new_frame_time
        fps = int(fps)
        print("fps:",fps)
        
        # frames = pipeline.wait_for_frames()

        # aligned_frames = align.process(frames)
        color_img = Vision.get_color_image()
        depth_img = Vision.get_depth_image()
        color_img = bridge.imgmsg_to_cv2(color_img, "passthrough")
        depth_img = bridge.imgmsg_to_cv2(depth_img, "passthrough")
        color_frame = color_img
        depth_frame = depth_img
        # if not depth_frame or not color_frame:
        #     continue

        img = np.asanyarray(color_frame)
        # img = np.asanyarray(color_frame.get_data())
        depth_image = np.asanyarray(depth_frame)
        # depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_image, alpha=0.08), cv2.COLORMAP_JET)
        
        # Letterbox
        im0 = img.copy()
        img = img[np.newaxis, :, :, :]        

        # cv2.imshow("Recognition result", im0)
        # cv2.waitKey(1)

        # Stack 堆疊
        img = np.stack(img, 0)

        # Convert 轉化
        img = img[..., ::-1].transpose((0, 3, 1, 2))  # BGR to RGB, BHWC to BCHW
        img = np.ascontiguousarray(img)


        img = torch.from_numpy(img).to(device)
        img = img.half() if half else img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if img.ndimension() == 3:
            img = img.unsqueeze(0)

        # Warmup
        if device.type != 'cpu' and (old_img_b != img.shape[0] or old_img_h != img.shape[2] or old_img_w != img.shape[3]):
            old_img_b = img.shape[0]
            old_img_h = img.shape[2]
            old_img_w = img.shape[3]
            for i in range(3):
                model(img, augment=opt.augment)[0]

        # Inference
        t1 = time_synchronized()
        with torch.no_grad():   # Calculating gradients would cause a GPU memory leak
            pred = model(img, augment=opt.augment)[0]
        t2 = time_synchronized()

        # Apply NMS
        pred = non_max_suppression(pred, opt.conf_thres, opt.iou_thres, classes=opt.classes, agnostic=opt.agnostic_nms)
        # print(pred)
        t3 = time_synchronized()


        # Process detections
        for i, det in enumerate(pred):  # detections per image

            # Produce an image of the same size as img
            width, height = im0.shape[1], im0.shape[0]
            img_mask = np.zeros((height, width), dtype=im0.dtype)

            gray = cv2.cvtColor(im0, cv2.COLOR_BGR2GRAY)   # 轉成灰階
            gray = cv2.medianBlur(gray, 7)                 # 模糊化，去除雜訊
            # gray_edge = cv2.Laplacian(gray, -1, 1, 3)      # 偵測邊緣cv2.Laplacian(img, ddepth, ksize, scale)
            # img 來源影像
            # ddepth 影像深度，設定 -1 表示使用圖片原本影像深度
            # ksize 運算區域大小，預設 1 ( 必須是正奇數 )
            # scale 縮放比例常數，預設 1 ( 必須是正奇數 )
            gray_edge = cv2.Canny(gray, 50, 50)                # 偵測邊緣cv2.Canny(img, threshold1, threshold2, apertureSize)
            # img 來源影像
            # threshold1 門檻值，範圍 0～255
            # threshold2 門檻值，範圍 0～255
            # apertureSize 計算梯度的 kernel size，預設 3

            kernel = np.ones((3,3), np.uint8)
            gray_edge = cv2.dilate(gray_edge, kernel, iterations = 3)
            gray_edge = cv2.erode(gray_edge, kernel, iterations = 1)
            # cv2.imshow("gray_edge",gray_edge)
            # gray_edge_inv = 255 - gray_edge
            color_edge = cv2.cvtColor(gray_edge, cv2.COLOR_GRAY2RGB)
            
            # p = Path(p)  # to Path
            # save_path = str(save_dir / p.name)  # img.jpg
            gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh

            right_line = []
            left_line = []
            for i in range(5):
                right_line.append((width, height))
                left_line.append((0, height))

            if len(det):
                # Rescale boxes from img_size to im0 size
                det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()

                # Print results
                for c in det[:, -1].unique():
                    n = (det[:, -1] == c).sum()  # detections per class
                    #s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string

                # Write results
                for *xyxy, conf, cls in reversed(det):
                    c = int(cls)  # integer class
                    label = f'{names[c]} {conf:.2f}'
                    plot_one_box(xyxy, im0, label=label, color=colors[int(cls)], line_thickness=2)
                    [right_line, left_line] = point_store(xyxy, im0, names[int(cls)], conf, right_line, left_line)
                    
                    mask(xyxy,img_mask, color_edge, label=label, color=colors[int(cls)], line_thickness=3)

                color_edge = cv2.add(color_edge, np.zeros(np.shape(im0), dtype=np.uint8), mask=img_mask)
                (x_goal, y_goal) = draw_line(im0, right_line, left_line)
                # print(right_line)
                # print("right_line = ", right_line)
                # print("left_line = ", left_line)
                # print("-----------------------------------------------")
                
            else:
                point_size = 10
                point_color_r = (0, 0, 255) # BGR
                thickness = 4 # 可以为 0 、4、8
                y_far = height / 2
                # initial
                y_mid = (height - y_far)*1/3 + y_far
                x_mid = width/2
                (x_goal, y_goal) = (int(x_mid), int(y_mid))
                cv2.circle(im0, (int(x_mid), int(y_mid)), point_size, point_color_r, thickness)

            # cv2.imshow("Recognition result depth",depth_colormap)
            # print((x_goal, y_goal))
            cv2.imshow("color_img", im0)
            cv2.imshow("color_edge result", color_edge)
            cv2.waitKey(1)

def gazebo_picture(save_img=False):
    frames = 1
    count = 1
    imgPath = './images/'
    while not rospy.is_shutdown():
        frames += 1
        color_img = Vision.get_color_image()
        depth_img = Vision.get_depth_image()
        color_img = bridge.imgmsg_to_cv2(color_img, "passthrough")
        depth_img = bridge.imgmsg_to_cv2(depth_img, "passthrough")
        if frames % 500 == 0:
            imgname = 'gazebo_' + str(count).rjust(3,'0') + ".jpg"
            newPath = imgPath + imgname
            cv2.imwrite(newPath, color_img, [cv2.IMWRITE_JPEG_QUALITY, 100])
            print("print! ", count)
            count += 1

        cv2.imshow('canny',color_img)
        cv2.waitKey(1)

def gazebo_video(save_img=False):
    frames = 1
    count = 1
    save_dir = './inference/gazebo_videos/'
    imgname = 'gazebo_videos.mp4'
    newPath = save_dir + imgname
    video_writer = cv2.VideoWriter(newPath, cv2.VideoWriter_fourcc(*'mp4v'), 120, (640, 480))
    while not rospy.is_shutdown():
        color_img = Vision.get_color_image()
        color_img = bridge.imgmsg_to_cv2(color_img, "passthrough")
        video_writer.write(color_img)
        cv2.imshow('color_img',color_img)
        cv2.waitKey(1)
    video_writer.release()

def goal_point(img):
    x = 0
    y = 0
    z = 0.35

    cv_image = bridge.imgmsg_to_cv2(img, "passthrough")
    kernel = np.ones((5, 5), np.uint8)
    cv_image = cv2.resize(cv_image, (0, 0), fx=1, fy=1)
    # print(cv_image)
    
    gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

    # O_P = min_max_filtering(M=1, N=70, I=gray)
    # O_P = O_P.astype(np.uint8)
    # cv2.imshow('O_P',O_P)
    # masked_edge_img=cv2.bitwise_and(erode,mask)   #与运算

    canny = cv2.Canny(cv_image,150,200)
    dilate = cv2.dilate(canny, kernel, iterations=10)
    erode = cv2.erode(dilate, kernel, iterations=5)
    cv2.imshow('canny',canny)

    # print(img.shape) 480*640
    # data =  canny[300, :]
    # print(type(O_P))
    return [x,y,z]


if __name__ == '__main__':
    rospy.init_node('get_goal_point')

    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', nargs='+', type=str, default='best_gazebo.pt', help='model.pt path(s)')
    parser.add_argument('--source', type=str, default='inference/images', help='source')  # file/folder, 0 for webcam
    parser.add_argument('--img-size', type=int, default=640, help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', action='store_true', help='display results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--nosave', action='store_true', help='do not save images/videos')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default='runs/detect', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--no-trace', action='store_true', help='don`t trace model')
    opt = parser.parse_args()
    # print(opt)
    check_requirements(exclude=('pycocotools', 'thop'))

    listener = tf.TransformListener()
    goal_publisher = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
    rate = rospy.Rate(100)
    # while not rospy.is_shutdown():
    #     try:
    #         (trans,rot) = listener.lookupTransform('/odom', '/base_link', rospy.Time(0))
    #     except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
    #         continue
        
    #     color_img = Vision.get_color_image()
    #     depth_img = Vision.get_depth_image()
    #     color_img = bridge.imgmsg_to_cv2(color_img, "passthrough")
    #     depth_img = bridge.imgmsg_to_cv2(depth_img, "passthrough")
    #     [goal_x,goal_y,goal_z] = goal_point(color_img)
    #     print('(x, y, z) = (',round(trans[0],6)+2, ' , ', round(trans[1],6)+2, ' , ', round(trans[2],6) ,')')
    #     cv2.waitKey(1)
    # with torch.no_grad():
    #     detect()
    detect()


    # gazebo_picture()
    # gazebo_video()

    
    cv2.waitKey(0)