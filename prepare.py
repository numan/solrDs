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

import os, sys, re, subprocess
import json, urllib2

from boto.ec2.connection import EC2Connection
from boto.ec2.regioninfo import RegionInfo

import administration
from route53 import Route53Zone

try:
	url = "http://169.254.169.254/latest/"

	userdata = json.load(urllib2.urlopen(url + "user-data"))
	instance_id = urllib2.urlopen(url + "meta-data/instance-id").read()
	hostname = urllib2.urlopen(url + "meta-data/public-hostname/").read()

	zone = urllib2.urlopen(url + "meta-data/placement/availability-zone").read()
	region = zone[:-1]

	zone_name = os.environ['HOSTED_ZONE_NAME']
	zone_id = os.environ['HOSTED_ZONE_ID']
except Exception as e:
	exit( "We couldn't get user-data or other meta-data...")

def provision(key, access, name, size, snapshot=None, device="/dev/sdf",
			mountpoint="/var/lib/fashiolista/solr"):
	region_info = RegionInfo(name=region,
							endpoint="ec2.{0}.amazonaws.com".format(region))
	ec2 = EC2Connection(key, access, region=region_info)
	r53_zone = Route53Zone(key, access, zone_id)

	def create_device(snapshot=None):
		# if we have the device (/dev/sdf) just don't do anything anymore
		mapping = ec2.get_instance_attribute(instance_id, 'blockDeviceMapping')
		print mapping
		try:
			volume_id = mapping['blockDeviceMapping'][device].volume_id
			print volume_id
		except:
			volume = ec2.create_volume(size, zone, snapshot)
			volume.attach(instance_id, device)
			volume_id = volume.id

		# we can't continue without a properly attached device
		os.system("while [ ! -b {0} ] ; do /bin/true ; done".format(device))

		# make sure the volume is deleted upon termination
		# should also protect from disaster like loosing an instance
		# (it doesn't work with boto, so we do it 'outside')
		os.system("/usr/bin/ec2-modify-instance-attribute --block-device-mapping \"{0}=:true\" {1} --region {2}".format(device, instance_id, region))

		# if we start from snapshot we are almost done
		if snapshot == "" or None == snapshot:
			# first create filesystem
			os.system("/sbin/mkfs.xfs {0}".format(device))

		# mount, but first wait until the device is ready
		os.system("/bin/mount -t xfs -o defaults {0} {1}".format(device, mountpoint))
		# and grow (if necessary)
		os.system("/usr/sbin/xfs_growfs {0}".format(mountpoint))

		return volume_id

	def prepare():
		# from this point we are sure we don't have to be careful
		# with local files/devices/disks/etc

		# we are going to work with local files, we need our path
		path = os.path.dirname(os.path.abspath(__file__))

		cron = "{0}/cron.d/solr.cron".format(path)

		# and root's cron will be set accordingly as well
		os.system("/bin/sed 's:INSTALLPATH:{0}:' {1} | /usr/bin/crontab".format(path, cron))

		# ok, ready to set up assets like bucket and volume
		# also, if we have a valid mount, we don't do anything
		if os.path.ismount(mountpoint) == False:
			try:
				# only try to create one if we have one
				if "" == snapshot or None == snapshot:
					raise Exception('metadata','empty snapshot')
				else:
					create_device(snapshot)
			except:
				try:
					latest = administration.get_latest_snapshot(key, access, name)
					create_device(latest)
				except:
					create_device()

		os.system("/bin/chown -R fashiolista.fashiolista {0}".format(mountpoint))

	try:
		prepare()
		ec2.create_tags( [instance_id], { "Name": name })

		r53_zone.create_record(name, hostname)
	except:
		print "{0} already exists".format(name)

def meminfo():
	"""
	dict of data from meminfo (str:int).
	Values are in kilobytes.
	"""
	re_parser = re.compile(r'^(?P<key>\S*):\s*(?P<value>\d*)\s*kB')
	result = dict()
	for line in open('/proc/meminfo'):
		match = re_parser.match(line)
		if not match:
			continue # skip lines that don't parse
		key, value = match.groups(['key', 'value'])
		result[key] = int(value)
	return result

if __name__ == '__main__':
	import os, sys

	# the name (and identity) of SOLR
	name = "{0}.{1}".format(userdata['name'],
						os.environ['HOSTED_ZONE_NAME'].rstrip('.'))

	# probably 2 x mem is enough
	try:
		size = userdata['size']
	except:
		size = 2 * ( meminfo()['MemTotal'] / ( 1024 * 1024 ) )

	try:
		snapshot = userdata['snapshot']
	except:
		snapshot = None

	provision(sys.argv[1], sys.argv[2], name, size, snapshot=snapshot)
