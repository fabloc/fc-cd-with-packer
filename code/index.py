#!/usr/bin/python
# -*- coding: utf-8 -*-
import logging,json,os,time,sys,re
from packerpy import PackerExecutable
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.auth.credentials import StsTokenCredential
from aliyunsdkoos.request.v20190601.StartExecutionRequest import StartExecutionRequest
from aliyunsdkoos.request.v20190601.ListExecutionsRequest import ListExecutionsRequest
from aliyunsdkess.request.v20140828.DescribeScalingGroupsRequest import DescribeScalingGroupsRequest

# if you open the initializer feature, please implement the initializer function, as below:
# def initializer(context):
#   logger = logging.getLogger()
#   logger.info('initializing')

def handler(event, context):

  access_key = context.credentials.accessKeyId
  secret_key = context.credentials.accessKeySecret
  security_token = context.credentials.securityToken
  region     = "eu-central-1"
  scaling_group_name = "asg-oos"
  logger = logging.getLogger()

  #Retrieve OSS File name from JSON Event
  evt = json.loads(event)
  oss_file_name = evt['events'][0]['oss']['object']['key']
  oss_folder_name = evt['events'][0]['oss']['bucket']['name']

  #Isolate base file name, without the ".zip" suffix
  regex_result = re.search(r"(?:.*\/)+(.+)(?:\.html)$", oss_file_name)

  #If matching groups are less then 1, it means that the file name is not correctly formatted. Exit the script
  if len(regex_result.groups()) < 1:
    return 1
  
  image_name = regex_result.group(1)
  logger.info("Image name: " + image_name)
  logger.info("Path to OSS file: " + oss_folder_name + '/' + oss_file_name)

  #Run packer inside the FC runtime. Assumption is that the packer executable is located in the "code" folder (default folder in the console)
  p = PackerExecutable("/code/packer")
  template = 'image-update.json'
  logger.info(p.version())
  os.environ['ALICLOUD_ACCESS_KEY'] = access_key
  os.environ['ALICLOUD_SECRET_KEY'] = secret_key
  os.environ['ALICLOUD_SECURITY_TOKEN'] = security_token
  os.environ['ALICLOUD_REGION'] = region
  os.environ['IMAGE_NAME'] = image_name
  os.environ['PATH_TO_RELEASE'] = oss_folder_name + '/' + oss_file_name

  (ret, out, err) = p.build(template)

  logger.info(out)

  #If there was an error, exist program
  if ret != 0:

    logger.error(err)
    return ret

  #If no error, carry on
  else:

    #Extract image_id from packer output. Generated image id can be found at the end of the output, suffixed by "\n"
    image_id = re.search(r"m-(?:.(?!m-))+(?:\n)$", out.decode("utf-8")).group(0).replace("\n", "")

    logger.info("Generated Image Id: " + image_id)

    #Retrieve Autoscaling Group information. Filtering is based on ASG name (no filtering available on Tags)
    sts_token_credential = StsTokenCredential(access_key, secret_key, security_token)
    client = AcsClient(region_id=region, credential=sts_token_credential)
    request = DescribeScalingGroupsRequest()
    request.set_accept_format('json')

    asg_id = ""

    asgListResponse = json.loads(client.do_action_with_exception(request))
    for scalingGroup in asgListResponse["ScalingGroups"]["ScalingGroup"]:
        if scalingGroup["ScalingGroupName"] == scaling_group_name:
            asg_id = scalingGroup["ScalingGroupId"]
            asg_config_id = scalingGroup["ActiveScalingConfigurationId"]
            break

    if asg_id == "":
        logger.error("Can't find Auto-Scaling Group with name: " + scaling_group_name)
        return 1

    logger.info("asg_id: " + asg_id)
    logger.info("asg_config_id: " + asg_config_id)

    #Execute a template.
    request = StartExecutionRequest()
    request.set_TemplateName("ACS-ESS-RollingUpdateByReplaceSystemDiskInScalingGroup")
    request.set_Parameters('''
    {
        "invokeType": "invoke",
        "scalingGroupId": "''' + asg_id + '''",
        "scalingConfigurationId": "''' + asg_config_id + '''",
        "imageId": "''' + image_id + '''",
        "OOSAssumeRole": "oosservicerole"
    }
    ''')

    logger.info(request.get_Parameters())

    executionResp = json.loads(client.do_action_with_exception(request))

    logger.info(executionResp)

    #Wait for the execution result

    request = ListExecutionsRequest()
    request.set_ExecutionId(executionResp["Execution"]["ExecutionId"])

    finished = False

    while not finished:
        plainResp = client.do_action_with_exception(request)
        sys.stdout.write('.')
        sys.stdout.flush()
        resp = json.loads(plainResp)
        finished = (resp["Executions"][0]["Status"] == "Success") or (resp["Executions"][0]["Status"] == "Failed")
        status = resp["Executions"][0]["Status"]
        time.sleep(1)
    
    logger.info("")
    logger.info ("Process complete with Status: " + status)

  return 0