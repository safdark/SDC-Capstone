#!/usr/bin/env python
import rospy
from std_msgs.msg import Int32
from geometry_msgs.msg import PoseStamped, Pose
from styx_msgs.msg import TrafficLightArray, TrafficLight
from styx_msgs.msg import Lane
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from light_classification.tl_classifier import TLClassifier
import tf
import cv2
import yaml

from waypoint_updater.waypoints_wrapper import WaypointsWrapper

STATE_COUNT_THRESHOLD = 3

class TLDetector(object):
    def __init__(self):
        rospy.init_node('tl_detector')

        self.pose = None
        self.waypoints = None
        self.waypoints_wrapper = None
        self.camera_image = None
        self.lights = []

        sub1 = rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb)
        sub2 = rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb)

        '''
        /vehicle/traffic_lights provides you with the location of the traffic light in 3D map space and
        helps you acquire an accurate ground truth data source for the traffic light
        classifier by sending the current color state of all traffic lights in the
        simulator. When testing on the vehicle, the color state will not be available. You'll need to
        rely on the position of the light and the camera image to predict it.
        '''
        sub3 = rospy.Subscriber('/vehicle/traffic_lights', TrafficLightArray, self.traffic_cb)
        sub6 = rospy.Subscriber('/image_color', Image, self.image_cb)

        config_string = rospy.get_param("/traffic_light_config")
        self.config = yaml.load(config_string)

        self.upcoming_red_light_pub = rospy.Publisher('/traffic_waypoint', Int32, queue_size=1)

        self.bridge = CvBridge()
        self.light_classifier = TLClassifier()
        self.listener = tf.TransformListener()

        self.state = TrafficLight.UNKNOWN
        self.last_state = TrafficLight.UNKNOWN
        self.last_redlight_wp = -1
        self.state_count = 0

        rospy.spin()

    def pose_cb(self, msg):
        self.pose = msg

    def waypoints_cb(self, msg):
        self.waypoints = msg
        self.waypoints_wrapper = WaypointsWrapper(msg.waypoints)

    def traffic_cb(self, msg):
        self.lights = msg.lights

    def image_cb(self, msg):
        """Identifies red lights in the incoming camera image and publishes the index
            of the waypoint closest to the red light's stop line to /traffic_waypoint

        Args:
            msg (Image): image from car-mounted camera

        """
        self.has_image = True
        self.camera_image = msg
        light_wp, state = self.process_traffic_lights()

        '''
        Publish upcoming red lights at camera frequency.
        Each predicted state has to occur `STATE_COUNT_THRESHOLD` number
        of times till we start using it. Otherwise the previous stable state is
        used.
        '''
        if self.state != state:
            # ~If it's a new state:
            self.state_count = 0
            self.state = state
        elif self.state_count >= STATE_COUNT_THRESHOLD:
            # ~If it's the same state but the state has 'stabilized':
            self.last_state = self.state
            self.last_redlight_wp = light_wp if state == TrafficLight.RED else -1
            self.upcoming_red_light_pub.publish(Int32(self.last_redlight_wp))
        else:
            #~If it's the same state but the state has not stabilized yet, we republish the old red-light waypoint (if any)
            self.upcoming_red_light_pub.publish(Int32(self.last_redlight_wp))
        self.state_count += 1

    def get_light_state(self, light):
        """Determines the current color of the traffic light
        Args:
            light (TrafficLight): light to classify
        Returns:
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)
        """
        # if(not self.has_image):
        #     self.prev_light_loc = None
        #     return False
        #
        # cv_image = self.bridge.imgmsg_to_cv2(self.camera_image, "bgr8")
        #
        # #Get classification
        # return self.light_classifier.get_classification(cv_image)
        return light.state

    def process_traffic_lights(self):
        """Finds closest visible traffic light, if one exists, and determines its
            location and color
        Returns:
            int: index of waypoint closes to the upcoming stop line for a traffic light (-1 if none exists)
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)
        """
        closest_light = None
        line_wp_idx = None

        # List of positions that correspond to the line to stop in front of, for a given intersection
        stop_line_positions = self.config['stop_line_positions']
        if self.pose is not None:
            car_wp_idx, _ = self.waypoints_wrapper.get_closest_waypoint_to([self.pose.pose.position.x, self.pose.pose.position.y])

            # Find the closest visible traffic light if one exists
            # Assume the closest light is at teh end of the waypoint list and iterate until we find the actual closest one
            # We do this, instead of using a KDTree, because there would likely be much fewer lights than waypoints,
            # so to build a KDTree out of the lights first would be a waste of time, given we could just iterate quickly over the lights
            closest_step_gap = len(self.waypoints.waypoints)
            for i, light in enumerate(self.lights):
                # Get stop line waypoint index:
                line = stop_line_positions[i]

                # Find waypoint closest to the stop line:
                tmp_line_wp_idx, _ = self.waypoints_wrapper.get_closest_waypoint_to([line[0], line[1]])

                # Check how many steps away the waypoint nearest to the line is, compared to the waypoint closest to the car
                step_gap = tmp_line_wp_idx - car_wp_idx

                # If the line is ahead of the car the step_gap will be positive
                # If the step gap is smaller than the closest step gap, we've found something closer
                if step_gap >= 0 and step_gap < closest_step_gap:
                    # ... and we update our knowledge of the closest light and the waypoint closest to its stopline
                    closest_step_gap = step_gap
                    closest_light = light
                    line_wp_idx = tmp_line_wp_idx

        if closest_light:
            state = self.get_light_state(closest_light)
            return line_wp_idx, state

        return -1, TrafficLight.UNKNOWN

if __name__ == '__main__':
    try:
        TLDetector()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start traffic node.')
