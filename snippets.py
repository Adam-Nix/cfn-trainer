"""Tested copy-paste snippets for the 'extra complexity' marks. Each is a fragment to merge into a template."""

SNIPPETS = {
    "params": ("Parameters: key pair, instance type, SSM AMI", """\
Parameters:
  KeyName:
    Type: AWS::EC2::KeyPair::KeyName
    Default: vockey
    Description: Existing key pair for SSH
  InstanceType:
    Type: String
    Default: t3.micro
    Description: EC2 instance size
  LatestAmiId:
    Type: AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>
    Default: /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64
"""),
    "constraints": ("Parameter constraints", """\
Parameters:
  InstanceType:
    Type: String
    Default: t3.micro
    AllowedValues: [t3.micro, t3.small, t3.medium]
    ConstraintDescription: Must be a permitted instance type
  VpcCidr:
    Type: String
    Default: 10.0.0.0/16
    AllowedPattern: '(\\d{1,3}\\.){3}\\d{1,3}/\\d{1,2}'
    ConstraintDescription: Must be a CIDR block like 10.0.0.0/16
  VolumeSize:
    Type: Number
    Default: 8
    MinValue: 8
    MaxValue: 100
"""),
    "ssm-ami": ("Latest AL2023 AMI without a parameter", """\
      ImageId: '{{resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64}}'
"""),
    "mappings": ("Mappings: AMI per region + FindInMap", """\
Mappings:
  RegionMap:
    us-east-1:
      AMI: ami-0fef201115eefe936   # AMI ids are region-specific -
    eu-west-1:
      AMI: ami-xxxxxxxxxxxxxxxxx   # look up the real AL2023 id for each region
# usage (inside an Instance's Properties):
#   ImageId: !FindInMap [RegionMap, !Ref 'AWS::Region', AMI]
"""),
    "conditions": ("Conditions: extra resource only in prod", """\
Parameters:
  Environment:
    Type: String
    Default: dev
    AllowedValues: [dev, prod]
Conditions:
  IsProd: !Equals [!Ref Environment, prod]
Resources:
  BackupServer:
    Type: AWS::EC2::Instance
    Condition: IsProd
    Properties:
      InstanceType: t3.small
      ImageId: ami-0fef201115eefe936
  WebServer:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: !If [IsProd, t3.small, t3.micro]
      ImageId: ami-0fef201115eefe936
Outputs:
  BackupIp:
    Condition: IsProd
    Value: !GetAtt BackupServer.PublicIp
"""),
    "rules": ("Rules: prod must use approved sizes", """\
Rules:
  ProdSizes:
    RuleCondition: !Equals [!Ref Environment, prod]
    Assertions:
      - Assert: !Contains [[t3.small, t3.medium], !Ref InstanceType]
        AssertDescription: Prod must use t3.small or t3.medium
"""),
    "interface": ("Metadata Interface: group parameters in the console", """\
Metadata:
  AWS::CloudFormation::Interface:
    ParameterGroups:
      - Label:
          default: Network settings
        Parameters: [VpcCidr]
      - Label:
          default: Server settings
        Parameters: [InstanceType, KeyName]
"""),
    "outputs": ("Outputs with Description + Export", """\
Outputs:
  VpcId:
    Description: ID of the VPC
    Value: !Ref AdamVPC
    Export:
      Name: !Sub '${AWS::StackName}-VpcId'
  WebUrl:
    Description: Website URL
    Value: !Sub 'http://${WebServer.PublicIp}'
"""),
    "tags": ("Tags on a resource", """\
      Tags:
        - Key: Name
          Value: !Sub '${AWS::StackName}-web'
        - Key: Environment
          Value: !Ref Environment
        - Key: Owner
          Value: student
"""),
    "deletion": ("DeletionPolicy / UpdateReplacePolicy", """\
  DataBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
    UpdateReplacePolicy: Retain
"""),
    "multi-az": ("Second subnet in another AZ", """\
  PublicSubnet2:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref AdamVPC
      AvailabilityZone: !Select [1, !GetAZs '']
      CidrBlock: 192.168.2.0/24
      MapPublicIpOnLaunch: true
"""),
    "nat": ("Private subnet + NAT gateway (see vpc-nat drill)", """\
  NatEIP:
    Type: AWS::EC2::EIP
    DependsOn: InternetGatewayAttachment
    Properties:
      Domain: vpc
  NatGateway:
    Type: AWS::EC2::NatGateway
    Properties:
      AllocationId: !GetAtt NatEIP.AllocationId
      SubnetId: !Ref PublicSubnet1
  PrivateRoute:
    Type: AWS::EC2::Route
    Properties:
      RouteTableId: !Ref PrivateRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      NatGatewayId: !Ref NatGateway
"""),
    "ssh-param": ("SSH only from your IP", """\
Parameters:
  SSHLocation:
    Type: String
    Description: Your public IPv4 followed by /32
    AllowedPattern: '(\\d{1,3}\\.){3}\\d{1,3}/32'
# usage in a security group rule:
#   - IpProtocol: tcp
#     FromPort: 22
#     ToPort: 22
#     CidrIp: !Ref SSHLocation
"""),
    "sg-to-sg": ("Allow from another security group", """\
  AllowAppToDb:
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      GroupId: !GetAtt DbSecurityGroup.GroupId
      IpProtocol: tcp
      FromPort: 3306
      ToPort: 3306
      SourceSecurityGroupId: !GetAtt AppSecurityGroup.GroupId
"""),
    "iam": ("IAM role + instance profile (needs CAPABILITY_IAM) - LIKELY BLOCKED in AWS Academy Learner Lab", """\
# WARNING: the Learner Lab reportedly forbids creating IAM roles. In the lab, attach the existing
# instance profile instead (check the name in your lab, often LabInstanceProfile):
#   IamInstanceProfile: LabInstanceProfile
  InstanceRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: ec2.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  InstanceProfile:
    Type: AWS::IAM::InstanceProfile
    Properties:
      Roles:
        - !Ref InstanceRole
# usage on the instance:  IamInstanceProfile: !Ref InstanceProfile
"""),
    "init-wait": ("cfn-init + WaitCondition (see init-waitcondition drill)", """\
  MyWaitHandle:
    Type: AWS::CloudFormation::WaitConditionHandle
  MyWaitCondition:
    Type: AWS::CloudFormation::WaitCondition
    DependsOn: WebServer
    Properties:
      Handle: !Ref MyWaitHandle
      Timeout: '300'
      Count: 1
"""),
    "depends": ("Explicit DependsOn", """\
  WebServer:
    Type: AWS::EC2::Instance
    DependsOn:
      - PublicRoute
      - RouteTableAssociationPublic1
"""),
    "extra": ("Cheap extra services: S3 bucket + CloudWatch alarm + SNS", """\
  AlertTopic:
    Type: AWS::SNS::Topic
  CpuAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmDescription: CPU above 80 percent
      Namespace: AWS/EC2
      MetricName: CPUUtilization
      Dimensions:
        - Name: InstanceId
          Value: !Ref WebServer
      Statistic: Average
      Period: 300
      EvaluationPeriods: 2
      Threshold: 80
      ComparisonOperator: GreaterThanThreshold
      AlarmActions:
        - !Ref AlertTopic
  LogsBucket:
    Type: AWS::S3::Bucket
    Properties:
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
"""),
}
