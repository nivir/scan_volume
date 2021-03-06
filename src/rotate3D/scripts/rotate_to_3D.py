#!/usr/bin/env python

import rospy
import rosbag
from sensor_msgs.msg import LaserScan
from sensor_msgs.msg import PointCloud2
import sensor_msgs.point_cloud2 as pc2
from sensor_msgs.msg import PointField
from std_msgs.msg import Int64
from laser_geometry import LaserProjection
import numpy as np
import matplotlib.pyplot as plt
import math
import os

BASE_DIR = os.path.dirname( os.path.abspath(__file__) )

# each scan is along x axis
# raw z is negative

def rotate_2d ( angle ):
    R = np.array( [ [ np.cos(angle), -np.sin( angle ) ],[ np.sin( angle  ), np.cos( angle ) ] ] )
    return R

class RotateTo3D:
    '''
    self.status: 'waitting' --start--> 'scanning' --stop--> 'waitting'
    '''
    def __init__(self):
        self.separate_models = False
        self.auto_pub_ref_at_frame = 5

        pi_angle = 41
        speed = 1.0 * math.pi / pi_angle
        fre = 49.5
        self.increment_theta = 1.0 * speed / fre
        self.z0_offset = 4 * 0.01
        #self.z0_offset = 10 * 0.01
        #self.z0_offset = 0 * 0.01

        self.status = 'waiting'
        self.pcl_3d = None
        self.all_3d_points_ls = []
        self.scanN = 0
        self.theta = math.pi * 0.2

        self.pcl_n = 0
        self.pcl_3d_pub = rospy.Publisher('pcl_3d',PointCloud2,queue_size=10)

        self.fig_dif = plt.figure()
        self.ax_dif = self.fig_dif.add_subplot(111)
        self.received_n = 0

        res_path = os.path.join( BASE_DIR,'3d_res' )
        if not os.path.exists( res_path ):
            os.makedirs( res_path )
        self.res_bag_name = os.path.join( res_path, 'pcl_3d-zofs_%d-piangle_%d-fre_%d.bag'%(self.z0_offset*100, pi_angle, fre*10) )
        self.pcl3d_bag = rosbag.Bag( self.res_bag_name,'w')
        rospy.loginfo( 'res path:%s'%(self.res_bag_name) )

    def start(self):
        self.status = 'start'
        self.scanN = 0
        self.pcl_3d = None
        self.all_3d_points_ls = []
        rospy.loginfo('received sart command')

    def stop(self):
        self.status = 'stop'
        rospy.loginfo('received stop command, theta: %0.2f'%(self.theta*180.0/math.pi))


    def from_2D_to_3D( self, point_2d ):
        x0 = point_2d[0]
        y0 = point_2d[1]

        self.theta = theta = self.scanN * self.increment_theta
        xy = np.matmul( rotate_2d( self.theta ), np.array( [[y0],[self.z0_offset]] ) )
        point_3d = [ xy[0,0], xy[1,0], x0, point_2d[3], point_2d[4] ]
        return point_3d


    #def from_2D_to_3D( self, point_2d ):
    #    x0 = point_2d[1]
    #    y0 = point_2d[0]
    #    self.theta = theta = self.scanN * self.increment_theta
    #    x = x0 * math.cos(theta)
    #    y = -x0 * math.sin(theta)
    #    z = y0
    #    point_3d = [x, y, z, point_2d[3], point_2d[4]]
    #    return point_3d

    def add_data( self, pcl_LaserScan, dif_start=None, dif_end=None ) :
        gen_data = pc2.read_points(pcl_LaserScan, field_names=None, skip_nans=True)
        curscan_points = []
        #if self.pcl_3d != None:
        #    gen_trunk = pc2.read_points(self.pcl_3d, field_names=None,skip_nans=True)
        #    for p in gen_trunk:
        #        curscan_points.append(list(p))

        for idx, p in enumerate(gen_data):
            if dif_start==None or ( idx >= dif_start and idx <= dif_end ):
                point_2d = list(p) #[ x,y,z,?,? ] z==0
                point_3d = self.from_2D_to_3D( point_2d  )
                curscan_points.append(point_3d)
                #if self.scanN % 100 == 0 and idx==0:
                #    rospy.loginfo( 'scanN=  %d, point_2d:%s,  point_3d:%s'%( self.scanN, point_2d, point_3d ) )

        self.all_3d_points_ls += curscan_points

        self.pcl_3d = pc2.create_cloud(pcl_LaserScan.header, pcl_LaserScan.fields, curscan_points)

    def xyz_from_pcl(self,pcl):
        gen = pc2.read_points(pcl, field_names=None, skip_nans=True)
        points = []
        for p in gen:
            xyz = np.array(list(p)[1:4])
            if points == []:
                points = xyz
            else:
                points = np.vstack((points,xyz))
        return points

    def update_scan_increment(self):
        '''
        do this at the end
	    '''
        self.increment = self.trunk_length / self.scanN
        rospy.loginfo('increment = %f / %d = %f',self.trunk_length,self.scanN,self.increment)


    def push(self,data_LaserScan):

        # rospy.loginfo('project data_LaserScan to PointCloud OK')
        pcl_LaserScan = LaserProjection().projectLaser(data_LaserScan)
        points_xyz = self.xyz_from_pcl(pcl_LaserScan)   # points_xyz: [N,3]  [:,1]=0
        # print "scan point N = ",points_xyz.shape[0],"   /  ", pcl_LaserScan.width, "    rangesN = ",len(data_LaserScan.ranges)

        if self.status == 'start' or self.status == 'scanning':
            if self.status == 'start':
                self.status = 'scanning'
            self.add_data( pcl_LaserScan )
            self.scanN += 1
            self.pcl_3d_pub.publish(self.pcl_3d)
            self.pcl3d_bag.write( 'pcl_3d', self.pcl_3d )

        elif self.status == 'stop':
            self.status = 'waitting'

            if self.separate_models:
                self.pcl_n = self.pcl_n + 1
                self.reset()

            self.pcl3d_bag.close()

            rospy.loginfo('stop recording, save this model: ' + self.res_bag_name )

        if self.status == 'scanning' and  self.theta > 181.0 * math.pi  / 180:
            self.stop()
        return self.scanN, self.theta


    def dif_range(self,points_xyz):
        '''
        Compare the difference between points_xyz and self.ref_points_xyz.
        Return the index of dif_start and dif_end
        '''
        min_N = min(points_xyz.shape[0],self.ref_points_xyz.shape[0])
        dif = points_xyz[0:min_N,self.height_axis] - self.ref_points_xyz[0:min_N,self.height_axis]
        dif = np.fabs(dif)
        threshold = self.dif_threshold
        dif_N = sum([ d > threshold for d in dif ])

        self.scan_difN_pub.publish(dif_N)
        if dif_N > 5:
            dif_start = len(dif)
            dif_end = 0
            for i,d in enumerate(dif):
                if dif_start==len(dif) and d > threshold and i+3<len(dif) and  dif[i+1] > threshold and dif[i+3] > threshold:
                    dif_start = i
                    self.scan_difStart_pub.publish(dif_start)

                if dif_start < len(dif) and i > dif_start and ( d < threshold or (d > threshold and i==len(dif)-1 ) ):
                    dif_end = i
                    self.scan_difEnd_pub.publish(dif_end)
                    if dif_end - dif_start > 3:
                            break
                    else:
                            # rospy.loginfo('short dif_range: dif_start= %d   dif_end= %d   dif_len= %d',dif_start,dif_end,dif_end-dif_start)
                            dif_start = len(dif)
                            dif_end = 0

            return True,dif_start,dif_end
        else:
            return False,0,0

    def volume_from_bag(self,model_bag_file):
        model_bag = rosbag.Bag(model_bag_file)
        msg_gen = model_bag.read_messages(topics='pcl_3d')
        for topic,msg,t in msg_gen:
            self. pcl_volume(msg)


if __name__ == '__main__':
    print 'in main'

    #TVD = RotateTo3D()
    #TVD.volume_from_bag('model_result_new/empty.bag')

