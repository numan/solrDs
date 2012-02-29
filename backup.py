# Copyright (C) 2011, 2012 9apps B.V.
# 
# This file is part of Redis for AWS.
# 
# Redis for AWS is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# Redis for AWS is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Redis for AWS. If not, see <http://www.gnu.org/licenses/>.

#
# Usage:
#	 backup.py <cmd> EC2_KEY_ID EC2_SECRET_KEY <expiration>
#
# <cmd>: snapshot or purge
# <expiration>: hourly (default), daily, weekly, monthly
#

import os, sys, subprocess
import json, urllib2

from time import gmtime,strftime,time

from boto.s3.connection import S3Connection
from boto.s3.connection import Location
from boto.ec2.connection import EC2Connection
from boto.ec2.regioninfo import RegionInfo
from boto.exception import S3CreateError
from boto.s3.key import Key

import administration

try:
    url = "http://169.254.169.254/latest/"

    userdata = json.load(urllib2.urlopen(url + "user-data"))
    instance_id = urllib2.urlopen(url + "meta-data/instance-id").read()
    hostname = urllib2.urlopen(url + "meta-data/public-hostname/").read()

    zone = urllib2.urlopen(url + "meta-data/placement/availability-zone").read()
    region = zone[:-1]
except Exception as e:
	print e
	exit( "We couldn't get user-data or other meta-data...")

# expiration in the future, calculated like this
days = 24 * 60 * 60
form = "%Y-%m-%d %H:%M:%S"
expires = {'hourly': strftime(form, gmtime(time() + 2 * days)),
		   'daily': strftime(form, gmtime(time() + 14 * days)),
		   'weekly': strftime(form, gmtime(time() + 61 * days)),
		   'monthly': strftime(form, gmtime(time() + 365 * days))}

def make_snapshot(key, access, name, expiration='hourly', device="/dev/sdf"):
	# first get the mountpoint (requires some energy, but we can...)
	df = subprocess.Popen(["/bin/df", device], stdout=subprocess.PIPE)
	output = df.communicate()[0]
	dummy, size, used, available, percent, mountpoint = \
							output.split("\n")[1].split()
	region_info = RegionInfo(name=region,
						endpoint="ec2.{0}.amazonaws.com".format(region))
	ec2 = EC2Connection(key, access, region=region_info)
	
	# if we have the device (/dev/sdf) just don't do anything anymore
	mapping = ec2.get_instance_attribute(instance_id, 'blockDeviceMapping')
	try:
		volume_id = mapping['blockDeviceMapping'][device].volume_id

		os.system("/usr/sbin/xfs_freeze -f {0}".format(mountpoint))
		snapshot = ec2.create_snapshot(volume_id,
					"Backup of {0} - for {1} - expires {2}".format(volume_id,
														name,
														expires[expiration]))
		os.system("/usr/sbin/xfs_freeze -u {0}".format(mountpoint))
	except Exception as e:
		print e

	return ["{0}".format(snapshot.id), expires[expiration]]

def purge_snapshots(key, access, name, snapshots):
	region_info = RegionInfo(name=region,
							endpoint="ec2.{0}.amazonaws.com".format(region))
	ec2 = EC2Connection(key, access, region=region_info)

	for snapshot in snapshots:
		if ec2.delete_snapshot(snapshot['snapshot']):
			print "deleting snapshot: {0}".format(snapshot['snapshot'])
			administration.delete_snapshot(key,
											access,
											name,
											snapshot['snapshot'])

# for convenience we can call this file to make backups directly
if __name__ == '__main__':
	# get the bucket, from the name
	name = userdata['name'].strip()
	hosted_zone = os.environ['HOSTED_ZONE_NAME'].rstrip('.')
	name = "{0}.{1}".format(name, hosted_zone)

	if "snapshot" == sys.argv[1]:
		backup = make_snapshot(sys.argv[2], sys.argv[3], name, sys.argv[4])
		administration.add_snapshot(sys.argv[2], sys.argv[3],
											name, backup)
	elif "purge" == sys.argv[1]:
		snapshots = administration.get_expired_snapshots(sys.argv[2],
											sys.argv[3], name)
		purge_snapshots(sys.argv[2], sys.argv[3], name, snapshots)

	elif "purge-all" == sys.argv[1]:
		snapshots = administration.get_all_snapshots(sys.argv[2],
											sys.argv[3], name)
		purge_snapshots(sys.argv[2], sys.argv[3], name, snapshots)
