#!/usr/bin/env python

import rospy
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan
from sensor_msgs.msg import PointCloud2
from sensor_msgs.msg import Image
from nav_msgs.msg import Odometry
from tf.transformations import euler_from_quaternion, quaternion_from_euler
import tf
import time
import math


class RobotSensor_vision():

    def __init__(self):
        self.d435_subscriber = rospy.Subscriber(
            '/camera/color/image_raw', Image, self.color_image_callback)
        self.d435_subscriber = rospy.Subscriber(
            '/camera/depth/image_raw', Image, self.depth_image_callback)
        self.color_image_msg =  Image()
        self.depth_image_msg =  PointCloud2()

        
    def color_image_callback(self, msg):
        self.color_image_msg = msg

    def depth_image_callback(self, msg):
        self.depth_image_msg = msg

    def get_color_image(self):
        # time.sleep(1)
        return self.color_image_msg
    
    def get_depth_image(self):
        # time.sleep(1)
        return self.depth_image_msg