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

import os, sys, subprocess
import json, urllib2

from boto.ec2.connection import EC2Connection
from boto.ec2.regioninfo import RegionInfo

import administration, backup
from route53 import Route53Zone

try:
	url = "http://169.254.169.254/latest/"

	userdata = json.load(urllib2.urlopen(url + "user-data"))
	instance_id = urllib2.urlopen(url + "meta-data/instance-id").read()
	hostname = urllib2.urlopen(url + "meta-data/public-hostname/").read()

	zone = urllib2.urlopen(url + "meta-data/placement/availability-zone").  read()
	region = zone[:-1]

	zone_name = os.environ['HOSTED_ZONE_NAME']
	zone_id = os.environ['HOSTED_ZONE_ID']
except Exception as e:
	exit( "We couldn't get user-data or other meta-data...")

def decommission(key, access, name, device="/dev/sdf"):
	def log(message, logging='warning'):
		"{0}: {1}, {2}".format('Decommission', message, logging)

	# first get the mountpoint (requires some energy, but we can...)
	df = subprocess.Popen(["/bin/df", device], stdout=subprocess.PIPE)
	output = df.communicate()[0]
	dummy, size, used, available, percent, mountpoint = \
							output.split("\n")[1].split()
	if device != dummy:
		log("No such device {0}".format(device), 'info')
		sys.exit()

	log('start dommissioning', 'info')

	# make a last snapshot
	log('and now a snapshot', 'info')
	snapshot = backup.make_snapshot(key, access, name, 'monthly')
	administration.add_snapshot(key, access, name, snapshot)

	# we don't have to get rid any the volume, it is deleted on termination

	# and empty the cron as well
	log('empty the cron', 'info')
	os.system("/bin/echo | /usr/bin/crontab")

	# make sure we make a clean AMI, with all monit checks monitored
	#log('finally, monitor all (monit), for making AMIs', 'info')
	#os.system("/usr/sbin/monit monitor all")

if __name__ == '__main__':
	import os, sys

	# the name (and identity) of the queue
	name = userdata['name']
	name = "{0}.{1}".format(name, zone_name.rstrip('.'))

	region_info = RegionInfo(name=region,
							endpoint="ec2.{0}.amazonaws.com".format(region))
	ec2 = EC2Connection(sys.argv[1], sys.argv[2], region=region_info)
	r53_zone = Route53Zone(sys.argv[1], sys.argv[2], zone_id)

	r53_zone.delete_record(name)

	decommission(sys.argv[1], sys.argv[2], name)
