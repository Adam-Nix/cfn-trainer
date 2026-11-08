"""Challenge definitions. Blanks are written @@answer||hint@@ - the student file shows ____N____,
the solution file shows the answer. Requirements are checked on the parsed template."""
import re

import cfnutil as U

MARK = re.compile(r"@@(.*?)\|\|(.*?)@@", re.S)


def build(ch):
    """-> (student_text, solution_text, [hints])"""
    hints = []

    def stu(m):
        hints.append(m.group(2).strip())
        return "____%d____" % len(hints)

    student = MARK.sub(stu, ch["template"])
    solution = MARK.sub(lambda m: m.group(1), ch["template"])
    if ch["kind"] == "debug":
        student, solution = ch["template"], ch["fixed"]
    return student, solution, hints


# ---------------------------------------------------------------- helpers
def _insts(t):
    return U.resources(t, "AWS::EC2::Instance")


def _vpc_cidr(t):
    for r in U.resources(t, "AWS::EC2::VPC").values():
        return U.net(U.props(r).get("CidrBlock"))


def _subnets_inside_vpc(t):
    v = _vpc_cidr(t)
    subs = U.resources(t, "AWS::EC2::Subnet")
    if v is None or not subs:
        return False, "no VPC/subnets"
    bad = [k for k, r in subs.items()
           if U.net(U.props(r).get("CidrBlock")) is None or not U.net(U.props(r).get("CidrBlock")).subnet_of(v)]
    return (not bad), ("subnet(s) outside VPC CIDR: " + ", ".join(bad)) if bad else ""


def _outputs_getatt(t, attr):
    n = 0
    for o in (t.get("Outputs") or {}).values():
        ga = U.getatt_of(o.get("Value")) if isinstance(o, dict) else None
        if ga and ga[1] == attr:
            n += 1
    return n


def _sg_uses_ids(t):
    bad = []
    for k, r in _insts(t).items():
        p = U.props(r)
        ids = p.get("SecurityGroupIds")
        ok = isinstance(ids, list) and ids and all(
            U.getatt_of(i) and U.getatt_of(i)[1] == "GroupId" or U.ref_of(i) for i in ids)
        if not ok:
            bad.append(k)
    return (not bad), ("use SecurityGroupIds + GetAtt GroupId on: " + ", ".join(bad)) if bad else ""


def _own_assoc_dep(t):
    """each instance DependsOn the route-table association of ITS OWN subnet"""
    assocs = U.resources(t, "AWS::EC2::SubnetRouteTableAssociation")
    bad = []
    for k, r in _insts(t).items():
        s = U.ref_of(U.props(r).get("SubnetId"))
        ok = any(d in assocs and U.ref_of(U.props(assocs[d]).get("SubnetId")) == s for d in U.depends_on(r))
        if not ok:
            bad.append(k)
    return (not bad), ("DependsOn the association for its own subnet: " + ", ".join(bad)) if bad else ""


def _truthy(v):
    """CloudFormation accepts true / 'true' / "True" for booleans."""
    return v is True or (isinstance(v, str) and v.lower() == "true")


def _userdata(r):
    return U.flat_text(U.props(r).get("UserData"))


# ---------------------------------------------------------------- C1
C1 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: Create 2 EC2 instances of Amazon Linux 2023 AMI

Resources:
  AnsibleSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Enable SSH access
      GroupName: ansible-lab-SG
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 22
          ToPort: 22
          CidrIp: 0.0.0.0/0
      Tags:
        - Key: Name
          Value: SG-allow-SSH

  controlinstance:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: t2.micro
      ImageId: @@ami-0fef201115eefe936||Amazon Linux 2023 AMI id (the labs used ami-0fef201115eefe936)@@
      SecurityGroups:
        - !Ref @@AnsibleSecurityGroup||logical id of the security group above@@
      KeyName: @@vockey||AWS Academy key pair name@@
      Tags:
        - Key: Name
          Value: control-node
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          yum update -y
          dnf install ansible -y

  managedinstance:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: t2.micro
      ImageId: @@ami-0fef201115eefe936||same AMI id for the managed node@@
      SecurityGroups:
        - !Ref @@AnsibleSecurityGroup||same security group@@
      KeyName: @@vockey||same key pair@@
      Tags:
        - Key: Name
          Value: managed-node
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          yum update -y

Outputs:
  controlinstanceId:
    Description: The Instance ID of the control-node
    Value: !Ref @@controlinstance||logical id of the control instance@@

  controlinstancePublicIP:
    Description: Public IP address of the control-node
    Value: !GetAtt controlinstance.@@PublicIp||GetAtt attribute that returns the public IPv4@@

  managedinstanceId:
    Description: The Instance ID of the managed-node
    Value: !Ref @@managedinstance||logical id of the managed instance@@

  managedPublicIP:
    Description: Public IP address of the managed-node
    Value: !GetAtt managedinstance.@@PublicIp||same attribute@@
"""

# ---------------------------------------------------------------- C2
C2 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: Two EC2 instances driven by parameters

Parameters:
  KeyPairName:
    Type: @@AWS::EC2::KeyPair::KeyName||AWS-specific parameter type that shows a key pair dropdown@@
    Description: Select an existing EC2 key pair for both instances

  InstanceType:
    Type: String
    Default: @@t2.micro||default size; must also appear in AllowedValues@@
    AllowedValues: @@[t2.micro, t2.small, t3.micro]||list of permitted instance types (flow style list)@@
    Description: EC2 instance type for both instances

Resources:
  AnsibleSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Enable SSH access
      GroupName: ansible-lab-SG
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 22
          ToPort: 22
          CidrIp: 0.0.0.0/0
      Tags:
        - Key: Name
          Value: SG-allow-SSH

  controlinstance:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: !Ref @@InstanceType||pass the parameter in@@
      ImageId: ami-0fef201115eefe936
      SecurityGroups:
        - !Ref AnsibleSecurityGroup
      KeyName: !Ref @@KeyPairName||pass the key parameter in@@
      Tags:
        - Key: Name
          Value: control node

  managedinstance:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: !Ref @@InstanceType||same parameter@@
      ImageId: ami-0fef201115eefe936
      SecurityGroups:
        - !Ref AnsibleSecurityGroup
      KeyName: !Ref @@KeyPairName||same parameter@@
      Tags:
        - Key: Name
          Value: managed node

Outputs:
  controlinstancePublicIP:
    Description: Public IP address of the control-node
    Value: !GetAtt controlinstance.PublicIp

  managedPublicIP:
    Description: Public IP address of the managed-node
    Value: !GetAtt managedinstance.PublicIp
"""

# ---------------------------------------------------------------- C3
C3 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: VPC with one public subnet (Lab 5 basic)

Resources:
  AdamVPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: @@192.168.0.0/16||VPC CIDR@@
      EnableDnsHostnames: @@true||needed so instances get DNS names@@
      EnableDnsSupport: true
      Tags:
        - Key: Name
          Value: Adam VPC

  AdamInternetGateway:
    Type: AWS::EC2::InternetGateway
    Properties:
      Tags:
        - Key: Name
          Value: AdamIGW

  InternetGatewayAttachment:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      InternetGatewayId: !Ref @@AdamInternetGateway||the gateway to attach@@
      VpcId: !Ref @@AdamVPC||the VPC to attach it to@@

  PublicSubnet1:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref AdamVPC
      AvailabilityZone: !Select [0, !GetAZs ""]
      CidrBlock: @@192.168.1.0/24||a /24 that sits INSIDE the VPC CIDR@@
      MapPublicIpOnLaunch: @@true||auto-assign public IPs in a public subnet@@
      Tags:
        - Key: Name
          Value: AdamPublicSubnet1

  AdamPublicRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref AdamVPC
      Tags:
        - Key: Name
          Value: PublicRouteTable

  PublicRoute:
    Type: AWS::EC2::Route
    DependsOn: @@InternetGatewayAttachment||route needs the IGW to be attached first@@
    Properties:
      RouteTableId: !Ref AdamPublicRouteTable
      DestinationCidrBlock: @@0.0.0.0/0||default route@@
      GatewayId: !Ref @@AdamInternetGateway||send it to the IGW@@

  RouteTableAssociationPublic1:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref @@PublicSubnet1||the subnet to make public@@
      RouteTableId: !Ref AdamPublicRouteTable

Outputs:
  VpcId:
    Value: !Ref AdamVPC
  PublicSubnetId:
    Value: !Ref PublicSubnet1
"""

# ---------------------------------------------------------------- C4
C4 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: VPC with public + private subnet and NAT gateway (Lab 5 NATGW)

Resources:
  AdamVPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 192.168.0.0/16
      EnableDnsHostnames: true
      EnableDnsSupport: true
      Tags:
        - Key: Name
          Value: Adam VPC

  AdamInternetGateway:
    Type: AWS::EC2::InternetGateway

  InternetGatewayAttachment:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      InternetGatewayId: !Ref AdamInternetGateway
      VpcId: !Ref AdamVPC

  PublicSubnet1:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref AdamVPC
      AvailabilityZone: !Select [0, !GetAZs ""]
      CidrBlock: 192.168.1.0/24
      MapPublicIpOnLaunch: true

  PrivateSubnet1:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref AdamVPC
      AvailabilityZone: !Select [1, !GetAZs ""]
      CidrBlock: 192.168.2.0/24
      MapPublicIpOnLaunch: @@false||private subnets must NOT hand out public IPs@@

  AdamPublicRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref AdamVPC

  PublicRoute:
    Type: AWS::EC2::Route
    DependsOn: InternetGatewayAttachment
    Properties:
      RouteTableId: !Ref AdamPublicRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref AdamInternetGateway

  RouteTableAssociationPublic1:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PublicSubnet1
      RouteTableId: !Ref AdamPublicRouteTable

  AdamNATGatewayEIP:
    Type: AWS::EC2::EIP
    DependsOn: InternetGatewayAttachment
    Properties:
      Domain: @@vpc||EIP domain for use in a VPC@@

  AdamNATGateway:
    Type: AWS::EC2::NatGateway
    Properties:
      AllocationId: !GetAtt AdamNATGatewayEIP.@@AllocationId||GetAtt attribute that NAT gateways need@@
      SubnetId: !Ref @@PublicSubnet1||the NAT gateway lives in a PUBLIC subnet@@

  AdamPrivateRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref AdamVPC

  PrivateRoute:
    Type: AWS::EC2::Route
    Properties:
      RouteTableId: !Ref AdamPrivateRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      NatGatewayId: !Ref @@AdamNATGateway||private traffic goes out via the NAT (the Ref also creates the dependency)@@

  RouteTableAssociationPrivate1:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref @@PrivateSubnet1||associate the PRIVATE subnet@@
      RouteTableId: !Ref @@AdamPrivateRouteTable||with the PRIVATE route table@@

Outputs:
  VpcId:
    Value: !Ref AdamVPC
  NatGatewayId:
    Value: !Ref AdamNATGateway
"""

# ---------------------------------------------------------------- C5
C5 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: VPC with two public subnets and a webserver in each (Lab 6 final combined)

Resources:
  AdamVPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 192.168.0.0/16
      EnableDnsHostnames: true
      EnableDnsSupport: true
      Tags:
        - Key: Name
          Value: Adam VPC

  AdamInternetGateway:
    Type: AWS::EC2::InternetGateway

  InternetGatewayAttachment:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      InternetGatewayId: !Ref AdamInternetGateway
      VpcId: !Ref AdamVPC

  PublicSubnet1:
    Type: AWS::EC2::Subnet
    Properties:
      AvailabilityZone: !Select [0, !GetAZs ""]
      CidrBlock: 192.168.1.0/24
      MapPublicIpOnLaunch: true
      VpcId: !Ref AdamVPC

  PublicSubnet2:
    Type: AWS::EC2::Subnet
    Properties:
      AvailabilityZone: !Select [@@1||second AZ = index 1@@, !GetAZs ""]
      CidrBlock: @@192.168.2.0/24||next /24 inside the VPC@@
      MapPublicIpOnLaunch: true
      VpcId: !Ref @@AdamVPC||subnet belongs to the VPC@@

  AdamPublicRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref AdamVPC

  PublicRoute:
    Type: AWS::EC2::Route
    DependsOn: InternetGatewayAttachment
    Properties:
      RouteTableId: !Ref AdamPublicRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref AdamInternetGateway

  RouteTableAssociationPublic1:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PublicSubnet1
      RouteTableId: !Ref AdamPublicRouteTable

  RouteTableAssociationPublic2:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref @@PublicSubnet2||associate subnet 2@@
      RouteTableId: !Ref AdamPublicRouteTable

  Allowhttp:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTP and HTTPS to Public Subnet
      GroupName: Adam SG
      VpcId: !Ref AdamVPC
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 0.0.0.0/0

  WebServerInstance1:
    Type: AWS::EC2::Instance
    DependsOn:
      - PublicRoute
      - RouteTableAssociationPublic1
    Properties:
      InstanceType: t2.small
      SubnetId: !Ref PublicSubnet1
      ImageId: ami-0fef201115eefe936
      SecurityGroupIds:
        - !GetAtt Allowhttp.@@GroupId||inside a non-default VPC use SecurityGroupIds + this attribute@@
      KeyName: vockey
      Tags:
        - Key: Name
          Value: Adam Web Server 1
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          dnf install httpd -y
          echo "<h1>Webserver 1 from stack ${AWS::StackName}</h1>" > /var/www/html/index.html
          systemctl enable --now httpd

  WebServerInstance2:
    Type: AWS::EC2::Instance
    DependsOn:
      - PublicRoute
      - @@RouteTableAssociationPublic2||depend on the association of ITS OWN subnet (the lab file had a bug here)@@
    Properties:
      InstanceType: t2.small
      SubnetId: !Ref @@PublicSubnet2||instance 2 goes in subnet 2@@
      ImageId: ami-0fef201115eefe936
      SecurityGroupIds:
        - !GetAtt Allowhttp.@@GroupId||same attribute@@
      KeyName: vockey
      Tags:
        - Key: Name
          Value: Adam Web Server 2
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          dnf install httpd -y
          echo "<h1>Webserver 2 from stack ${AWS::StackName}</h1>" > /var/www/html/index.html
          systemctl enable --now httpd

Outputs:
  WebServerPublicIP1:
    Description: Public IP of web server 1
    Value: !GetAtt WebServerInstance1.@@PublicIp||attribute for the public IPv4@@

  WebServerPublicIP2:
    Description: Public IP of web server 2
    Value: !GetAtt WebServerInstance2.@@PublicIp||same@@

  VpcId:
    Value: !Ref AdamVPC
"""

# ---------------------------------------------------------------- C6 (network stack w/ exports)
C6 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: Network stack - public and private subnets, IGW, NAT and web security group (Part 1 of 2)

Parameters:
  SSHLocation:
    Type: String
    Description: Your public IPv4 address followed by /32, for SSH to the public server.
    AllowedPattern: '@@(\d{1,3}\.){3}\d{1,3}/32||regex: four dotted number groups then /32@@'
    ConstraintDescription: Enter your public IPv4 address followed by /32.

Resources:
  adamVPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 192.168.77.0/24
      EnableDnsSupport: true
      EnableDnsHostnames: true
      Tags:
        - Key: Name
          Value: adam-VPC

  PublicSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref adamVPC
      CidrBlock: 192.168.77.0/25
      AvailabilityZone: !Select [0, !GetAZs '']
      MapPublicIpOnLaunch: true

  PrivateSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref adamVPC
      CidrBlock: @@192.168.77.128/25||the other half of the /24, must not overlap the public /25@@
      AvailabilityZone: !Select [0, !GetAZs '']
      MapPublicIpOnLaunch: false

  InternetGateway:
    Type: AWS::EC2::InternetGateway

  AttachGateway:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref adamVPC
      InternetGatewayId: !Ref InternetGateway

  PublicRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref adamVPC

  PublicInternetRoute:
    Type: AWS::EC2::Route
    DependsOn: AttachGateway
    Properties:
      RouteTableId: !Ref PublicRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway

  PublicSubnetAssociation:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PublicSubnet
      RouteTableId: !Ref PublicRouteTable

  NatElasticIP:
    Type: AWS::EC2::EIP
    DependsOn: AttachGateway
    Properties:
      Domain: vpc

  NatGateway:
    Type: AWS::EC2::NatGateway
    DependsOn: AttachGateway
    Properties:
      AllocationId: !GetAtt NatElasticIP.@@AllocationId||attribute NAT needs@@
      SubnetId: !Ref @@PublicSubnet||NAT goes in the public subnet@@

  PrivateRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref adamVPC

  PrivateInternetRoute:
    Type: AWS::EC2::Route
    Properties:
      RouteTableId: !Ref PrivateRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      NatGatewayId: !Ref NatGateway

  PrivateSubnetAssociation:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PrivateSubnet
      RouteTableId: !Ref PrivateRouteTable

  WebSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTP and SSH for the webservers
      GroupName: Adam-SG Allow http and SSH
      VpcId: !Ref adamVPC
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0
        - IpProtocol: tcp
          FromPort: 22
          ToPort: 22
          CidrIp: !Ref @@SSHLocation||only YOUR ip may ssh in - use the parameter@@
        - IpProtocol: tcp
          FromPort: 22
          ToPort: 22
          CidrIp: 192.168.77.0/24

Outputs:
  VPCId:
    Value: !Ref adamVPC
    Export:
      Name: !Sub '${AWS::StackName}-@@VPCId||export suffix, ends up as <stack>-VPCId@@'
  PublicSubnetId:
    Value: !Ref PublicSubnet
    Export:
      Name: !Sub '${AWS::StackName}-@@PublicSubnetId||export suffix@@'
  PrivateSubnetId:
    Value: !Ref PrivateSubnet
    Export:
      Name: !Sub '${AWS::StackName}-PrivateSubnetId'
  WebSecurityGroupId:
    Value: !GetAtt WebSecurityGroup.@@GroupId||attribute holding the sg-xxxx id@@
    Export:
      Name: !Sub '${AWS::StackName}-WebSecurityGroupId'
"""

# ---------------------------------------------------------------- C7 (servers stack importing)
C7 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: Two Apache webservers using subnets and a security group exported by the network stack (Part 2 of 2)

Parameters:
  NetworkStackName:
    Type: String
    Default: adam-network
    Description: Exact name of the already-created network stack.
  KeyName:
    Type: @@AWS::EC2::KeyPair::KeyName||key pair dropdown type@@
    Default: vockey
  LatestAmiId:
    Type: AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>
    Default: /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64

Resources:
  PublicWebServer:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: !Ref LatestAmiId
      InstanceType: t3.micro
      KeyName: !Ref @@KeyName||parameter above@@
      SubnetId:
        Fn::ImportValue: !Sub '${NetworkStackName}-@@PublicSubnetId||name the network stack exported@@'
      SecurityGroupIds:
        - Fn::ImportValue: !Sub '${NetworkStackName}-@@WebSecurityGroupId||name the network stack exported@@'
      Tags:
        - Key: Name
          Value: adam-Public-WebServer
      UserData:
        Fn::Base64: |
          #!/bin/bash
          set -eu
          dnf install -y httpd
          echo '<h1>adam public webserver</h1>' > /var/www/html/index.html
          systemctl enable --now httpd

  PrivateWebServer:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: !Ref LatestAmiId
      InstanceType: t3.micro
      KeyName: !Ref KeyName
      SubnetId:
        Fn::ImportValue: !Sub '${NetworkStackName}-@@PrivateSubnetId||the PRIVATE subnet export@@'
      SecurityGroupIds:
        - Fn::ImportValue: !Sub '${NetworkStackName}-WebSecurityGroupId'
      Tags:
        - Key: Name
          Value: adam-Private-WebServer
      UserData:
        Fn::Base64: |
          #!/bin/bash
          set -eu
          dnf install -y httpd
          echo '<h1>adam private webserver</h1>' > /var/www/html/index.html
          systemctl enable --now httpd

Outputs:
  PublicWebsiteURL:
    Description: Open this URL after Apache finishes installing.
    Value: !Sub 'http://${PublicWebServer.@@PublicIp||attribute for public IPv4@@}'
  PrivateServerPrivateIP:
    Description: Private IP of the private server
    Value: !GetAtt PrivateWebServer.@@PrivateIp||attribute for private IPv4@@
"""

# ---------------------------------------------------------------- C8
C8 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: Apache using cfn-init and a WaitCondition

Resources:
  WebSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTP and SSH access
      GroupName: Adam-class-SG1
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0
        - IpProtocol: tcp
          FromPort: 22
          ToPort: 22
          CidrIp: 0.0.0.0/0

  MyWaitHandle:
    Type: @@AWS::CloudFormation::WaitConditionHandle||presigned-URL resource the instance signals to@@

  WebServer:
    Type: AWS::EC2::Instance
    Metadata:
      @@AWS::CloudFormation::Init||resource-level metadata key that cfn-init reads@@:
        config:
          commands:
            01_install_apache:
              command: "dnf install -y @@httpd||package name@@"
            02_start_service:
              command: "systemctl enable --now httpd"
          files:
            /var/www/html/index.html:
              content: "Apache configured using CloudFormation Init"
              mode: "000644"
              owner: root
              group: root
    Properties:
      ImageId: ami-0567589d25e06853e
      InstanceType: t3.micro
      SecurityGroups:
        - !Ref WebSecurityGroup
      Tags:
        - Key: Name
          Value: Init-WebServer
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          dnf install -y aws-cfn-bootstrap || exit 1
          /opt/aws/bin/cfn-init -v --stack '${AWS::StackName}' --resource @@WebServer||logical id that holds the Init metadata@@ --region '${AWS::Region}'
          /opt/aws/bin/cfn-signal -e @@$?||exit status of the previous command@@ --id WebServer '${MyWaitHandle}'

  MyWaitCondition:
    Type: AWS::CloudFormation::WaitCondition
    DependsOn: @@WebServer||wait condition is created AFTER the instance@@
    Properties:
      Handle: !Ref @@MyWaitHandle||the handle to wait on@@
      Timeout: '@@300||seconds to wait before rollback@@'
      Count: @@1||number of success signals expected@@

Outputs:
  WebsiteURL:
    Value: !Sub 'http://${WebServer.PublicIp}'
"""

# ---------------------------------------------------------------- DEBUG 1
D1 = r"""AWSTemplateFormatVersion: '2010-09-9'
Description: Debug drill 1 - a web server in the default VPC

Parameters:
  KeyPairName:
    Type: AWS::EC2::KeyPair::KeyName

Resources:
  WebSG:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTP
      SecurityGroupIngres:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0

  WebServer:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: t2.micro
      ImageId: ami-0fef201115eefe936
      KeyName: !Ref KeyPairname
      SecurityGroups:
        - !Ref WebSecurityGroup
      UserData:
        Fn::Base64: |
          #!/bin/bash
          dnf install -y httpd
          systemctl enable --now httpd

Outputs:
  WebIP:
    Value: !GetAtt WebServer.PublicIP
"""
D1_FIXED = D1.replace("'2010-09-9'", "'2010-09-09'").replace("SecurityGroupIngres", "SecurityGroupIngress") \
    .replace("KeyPairname", "KeyPairName").replace("!Ref WebSecurityGroup", "!Ref WebSG") \
    .replace("PublicIP", "PublicIp")

# ---------------------------------------------------------------- DEBUG 2
D2 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: Debug drill 2 - network LOGIC bugs. cfn-lint only catches some of them.
# Symptoms: private subnet can't reach the internet, public subnet is not really public,
# the instance fails with a security group error, and a subnet is rejected as invalid.
# Lint flags 2 bugs; the requirement list reveals what lint cannot see.

Resources:
  VPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.0.0.0/16
      EnableDnsSupport: true
      EnableDnsHostnames: true

  IGW:
    Type: AWS::EC2::InternetGateway

  IGWAttach:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref VPC
      InternetGatewayId: !Ref IGW

  PublicSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.1.0/24
      MapPublicIpOnLaunch: true

  PrivateSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.1.2.0/24

  PublicRT:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref VPC

  PublicRoute:
    Type: AWS::EC2::Route
    Properties:
      RouteTableId: !Ref PublicRT
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref IGW

  PrivateRT:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref VPC

  PrivateRoute:
    Type: AWS::EC2::Route
    Properties:
      RouteTableId: !Ref PrivateRT
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref IGW

  PrivateAssoc:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PrivateSubnet
      RouteTableId: !Ref PrivateRT

  NatEIP:
    Type: AWS::EC2::EIP
    Properties:
      Domain: vpc

  Nat:
    Type: AWS::EC2::NatGateway
    Properties:
      AllocationId: !GetAtt NatEIP.AllocationId
      SubnetId: !Ref PrivateSubnet

  WebSG:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTP
      VpcId: !Ref VPC
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0

  Web:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: t2.micro
      ImageId: ami-0fef201115eefe936
      SubnetId: !Ref PublicSubnet
      SecurityGroups:
        - !Ref WebSG
"""
D2_FIXED = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: Debug drill 2 - fixed

Resources:
  VPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.0.0.0/16
      EnableDnsSupport: true
      EnableDnsHostnames: true

  IGW:
    Type: AWS::EC2::InternetGateway

  IGWAttach:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref VPC
      InternetGatewayId: !Ref IGW

  PublicSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.1.0/24
      MapPublicIpOnLaunch: true

  PrivateSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.2.0/24

  PublicRT:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref VPC

  PublicRoute:
    Type: AWS::EC2::Route
    DependsOn: IGWAttach
    Properties:
      RouteTableId: !Ref PublicRT
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref IGW

  PublicAssoc:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PublicSubnet
      RouteTableId: !Ref PublicRT

  PrivateRT:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref VPC

  PrivateRoute:
    Type: AWS::EC2::Route
    Properties:
      RouteTableId: !Ref PrivateRT
      DestinationCidrBlock: 0.0.0.0/0
      NatGatewayId: !Ref Nat

  PrivateAssoc:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PrivateSubnet
      RouteTableId: !Ref PrivateRT

  NatEIP:
    Type: AWS::EC2::EIP
    DependsOn: IGWAttach
    Properties:
      Domain: vpc

  Nat:
    Type: AWS::EC2::NatGateway
    Properties:
      AllocationId: !GetAtt NatEIP.AllocationId
      SubnetId: !Ref PublicSubnet

  WebSG:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTP
      VpcId: !Ref VPC
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0

  Web:
    Type: AWS::EC2::Instance
    DependsOn: PublicAssoc
    Properties:
      InstanceType: t2.micro
      ImageId: ami-0fef201115eefe936
      SubnetId: !Ref PublicSubnet
      SecurityGroupIds:
        - !GetAtt WebSG.GroupId
"""

# ---------------------------------------------------------------- DEBUG 3
D3 = r"""AWSTemplateFormatVersion: '2010-09-09'
Description: Debug drill 3 - parameters, mappings and conditions

Parameters:
  Environment:
    Type: String
    Default: staging
    AllowedValues: [dev, prod]
  InstanceType:
    Type: String
    Default: t2.micro
    AllowedValues: [t2.micro, t2.small]

Mappings:
  RegionMap:
    us-east-1:
      AMI: ami-0fef201115eefe936
    eu-west-1:
      AMI: ami-0fef201115eefe936

Conditions:
  IsProd: !Equals [!Ref Environment, prod]

Resources:
  WebServer:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: !If [IsProduction, t2.small, !Ref InstanceType]
      ImageId: !FindInMap [RegionMap, !Ref 'AWS::Region', AMI]
      Tags:
        - Key: Name
          Value: web

  BackupServer:
    Type: AWS::EC2::Instance
    Condition: IsProd
    Properties:
      InstanceType: !Ref InstanceTyp
      ImageId: !FindInMap [RegionMap, !Ref 'AWS::Region', AMi]
      Tags:
        - Key: Name
          Value: backup

Outputs:
  WebIp:
    Value: !GetAtt WebServer.PublicIp
  BackupIp:
    Value: !GetAtt BackupServer.PublicIp
"""
D3_FIXED = D3.replace("Default: staging", "Default: dev").replace("IsProduction", "IsProd") \
    .replace("InstanceTyp\n", "InstanceType\n").replace("AMi]", "AMI]") \
    .replace("  BackupIp:\n    Value:", "  BackupIp:\n    Condition: IsProd\n    Value:")


# ---------------------------------------------------------------- requirement sets
def _r(desc, fn):
    return (desc, fn)


REQ_C1 = [
    _r("Exactly 2 EC2 instances", lambda t: len(_insts(t)) == 2),
    _r("Security group allows SSH (port 22)", lambda t: any(
        str(rule.get("FromPort")) == "22" for _, rule in U.sg_ingress_rules(t))),
    _r("Both ImageIds are an AMI id (ami-...) or an SSM reference", lambda t: all(
        re.fullmatch(r"ami-[0-9a-f]{8}([0-9a-f]{9})?", str(U.props(r).get("ImageId")))
        or "resolve:ssm" in str(U.props(r).get("ImageId")) for r in _insts(t).values())),
    _r("Both instances have a KeyName", lambda t: all(U.props(r).get("KeyName") for r in _insts(t).values())),
    _r("Both instances attach the security group", lambda t: all(
        any(U.mentions(s, sg) for s in (U.props(r).get("SecurityGroups") or []) + (U.props(r).get("SecurityGroupIds") or [])
            for sg in U.resources(t, "AWS::EC2::SecurityGroup"))
        for r in _insts(t).values())),
    _r("Two outputs use !GetAtt <instance>.PublicIp", lambda t: _outputs_getatt(t, "PublicIp") >= 2),
]

REQ_C2 = [
    _r("KeyPairName has type AWS::EC2::KeyPair::KeyName", lambda t: (t.get("Parameters", {}).get("KeyPairName") or {}).get(
        "Type") == "AWS::EC2::KeyPair::KeyName"),
    _r("InstanceType has AllowedValues (2+) and the Default is one of them", lambda t: (lambda p: bool(
        isinstance(p.get("AllowedValues"), list) and len(p["AllowedValues"]) >= 2 and p.get("Default") in p["AllowedValues"]
    ))(t.get("Parameters", {}).get("InstanceType") or {})),
    _r("Both instances take InstanceType from the parameter", lambda t: all(
        U.ref_of(U.props(r).get("InstanceType")) == "InstanceType" for r in _insts(t).values()) and len(_insts(t)) == 2),
    _r("Both instances take KeyName from the parameter", lambda t: all(
        U.ref_of(U.props(r).get("KeyName")) == "KeyPairName" for r in _insts(t).values()) and len(_insts(t)) == 2),
]

REQ_C3 = [
    _r("Subnet CIDR is inside the VPC CIDR", _subnets_inside_vpc),
    _r("Public route: 0.0.0.0/0 -> the Internet Gateway", lambda t: any(v["igw"] for v in U.route_tables(t).values())),
    _r("Subnet is associated with the route table that has the IGW route", lambda t: bool(U.public_subnets(t))),
    _r("IGW is attached to the VPC", lambda t: any(
        U.ref_of(U.props(r).get("VpcId")) in U.resources(t, "AWS::EC2::VPC") for r in
        U.resources(t, "AWS::EC2::VPCGatewayAttachment").values())),
    _r("Route has DependsOn the gateway attachment", lambda t: any(
        U.depends_on(r) for r in U.resources(t, "AWS::EC2::Route").values())),
    _r("Subnet sets MapPublicIpOnLaunch true", lambda t: any(
        _truthy(U.props(r).get("MapPublicIpOnLaunch")) for r in U.resources(t, "AWS::EC2::Subnet").values())),
    _r("VPC has EnableDnsHostnames true", lambda t: all(
        _truthy(U.props(r).get("EnableDnsHostnames")) for r in U.resources(t, "AWS::EC2::VPC").values())),
]

REQ_C4 = [
    _r("Public subnet exists (route to IGW)", lambda t: bool(U.public_subnets(t))),
    _r("Private subnet exists (route to NAT)", lambda t: bool(U.private_subnets(t))),
    _r("NAT gateway sits in a PUBLIC subnet", lambda t: all(
        U.ref_of(U.props(r).get("SubnetId")) in U.public_subnets(t) for r in U.resources(t, "AWS::EC2::NatGateway").values())
        and bool(U.resources(t, "AWS::EC2::NatGateway"))),
    _r("NAT uses an EIP via !GetAtt ...AllocationId", lambda t: all(
        (U.getatt_of(U.props(r).get("AllocationId")) or ("", ""))[1] == "AllocationId"
        for r in U.resources(t, "AWS::EC2::NatGateway").values()) and bool(U.resources(t, "AWS::EC2::NatGateway"))),
    _r("EIP Domain is vpc", lambda t: all(
        U.props(r).get("Domain") == "vpc" for r in U.resources(t, "AWS::EC2::EIP").values()) and bool(
        U.resources(t, "AWS::EC2::EIP"))),
    _r("Private subnet does not auto-assign public IPs", lambda t: all(
        not _truthy(U.props(U.resources(t, "AWS::EC2::Subnet")[s]).get("MapPublicIpOnLaunch"))
        for s in U.private_subnets(t)) and bool(U.private_subnets(t))),
]

REQ_C5 = [
    _r("Two instances in different subnets", lambda t: len({U.ref_of(U.props(r).get("SubnetId"))
                                                         for r in _insts(t).values()}) == 2),
    _r("Subnets are inside the VPC CIDR", _subnets_inside_vpc),
    _r("Subnets are in different AZs", lambda t: len({repr(U.props(r).get("AvailabilityZone"))
                                                    for r in U.resources(t, "AWS::EC2::Subnet").values()}) == 2),
    _r("Both subnets are public (associated to the IGW route table)", lambda t: len(U.public_subnets(t)) == 2),
    _r("Instances use SecurityGroupIds + !GetAtt GroupId", _sg_uses_ids),
    _r("Each instance DependsOn the association of its OWN subnet", _own_assoc_dep),
    _r("Two public IP outputs", lambda t: _outputs_getatt(t, "PublicIp") >= 2),
]

REQ_C6 = [
    _r("Subnets are inside the VPC CIDR", _subnets_inside_vpc),
    _r("Public and private subnets do not overlap", lambda t: (lambda n: len(n) == 2 and not n[0].overlaps(n[1]))(
        [U.net(U.props(r).get("CidrBlock")) for r in U.resources(t, "AWS::EC2::Subnet").values()
         if U.net(U.props(r).get("CidrBlock"))])),
    _r("SSHLocation AllowedPattern accepts 1.2.3.4/32 and rejects 1.2.3.4", lambda t: (lambda p: bool(
        p and re.fullmatch(p, "1.2.3.4/32") and not re.fullmatch(p, "1.2.3.4")))(
        (t.get("Parameters", {}).get("SSHLocation") or {}).get("AllowedPattern"))),
    _r("SSH from the internet uses !Ref SSHLocation", lambda t: any(
        U.ref_of(rule.get("CidrIp")) == "SSHLocation" for _, rule in U.sg_ingress_rules(t))),
    _r("Exports VPCId, PublicSubnetId, PrivateSubnetId, WebSecurityGroupId named <stack>-<Name>", lambda t: (lambda o: all(
        any(isinstance(v, dict) and "Export" in v and _export_name(v["Export"].get("Name")) == "${AWS::StackName}-" + n
            for v in o.values())
        for n in ("VPCId", "PublicSubnetId", "PrivateSubnetId", "WebSecurityGroupId")))(t.get("Outputs") or {})),
    _r("NAT in public subnet, private route via NAT", lambda t: bool(U.private_subnets(t)) and all(
        U.ref_of(U.props(r).get("SubnetId")) in U.public_subnets(t)
        for r in U.resources(t, "AWS::EC2::NatGateway").values())),
]

_EXPORTS = {"VPCId", "PublicSubnetId", "PrivateSubnetId", "WebSecurityGroupId"}


def _export_name(v):
    """Normalise !Sub '${X}-Y' and !Join ['-', [!Ref X, Y]] to the string '${X}-Y'."""
    if isinstance(v, dict) and "Fn::Sub" in v:
        s = v["Fn::Sub"]
        return s[0] if isinstance(s, list) else str(s)
    if isinstance(v, dict) and "Fn::Join" in v:
        sep, parts = v["Fn::Join"]
        return sep.join("${%s}" % U.ref_of(p) if U.ref_of(p) else str(p) for p in parts)
    return str(v)


def _import_suffixes(t):
    out = []
    for n in U.walk(t.get("Resources")):
        if isinstance(n, dict) and "Fn::ImportValue" in n:
            out.append(_export_name(n["Fn::ImportValue"]))
    return out


REQ_C7 = [
    _r("KeyName parameter type is AWS::EC2::KeyPair::KeyName", lambda t: (t.get("Parameters", {}).get("KeyName") or {}).get(
        "Type") == "AWS::EC2::KeyPair::KeyName"),
    _r("Every ImportValue is '${NetworkStackName}-<export that exists>'", lambda t: bool(_import_suffixes(t)) and all(
        s.startswith("${NetworkStackName}-") and s.split("-", 1)[1] in _EXPORTS for s in _import_suffixes(t))),
    _r("Public server imports the PUBLIC subnet", lambda t: "PublicSubnetId" in str(
        U.props(U.resources(t)["PublicWebServer"]).get("SubnetId"))),
    _r("Private server imports the PRIVATE subnet", lambda t: "PrivateSubnetId" in str(
        U.props(U.resources(t)["PrivateWebServer"]).get("SubnetId"))),
    _r("Outputs use PublicIp and PrivateIp attributes", lambda t: _outputs_getatt(t, "PrivateIp") >= 1 and "PublicIp" in str(
        (t.get("Outputs") or {}).get("PublicWebsiteURL"))),
]


def _c8_inst(t):
    r = U.resources(t, "AWS::EC2::Instance")
    return next(iter(r.values())) if r else {}


REQ_C8 = [
    _r("WaitConditionHandle resource exists", lambda t: bool(U.resources(t, "AWS::CloudFormation::WaitConditionHandle"))),
    _r("Instance Metadata has AWS::CloudFormation::Init", lambda t: "AWS::CloudFormation::Init" in (
        _c8_inst(t).get("Metadata") or {})),
    _r("Init installs httpd and has a files section", lambda t: "httpd" in U.flat_text(
        (_c8_inst(t).get("Metadata") or {})) and "files" in str(_c8_inst(t).get("Metadata"))),
    _r("UserData runs cfn-init for resource WebServer", lambda t: "cfn-init" in _userdata(_c8_inst(t)) and
       "--resource WebServer" in _userdata(_c8_inst(t))),
    _r("UserData signals with cfn-signal -e $? (or --exit-code $?)", lambda t: re.search(
        r"cfn-signal\s+(-e|--exit-code)\s+\$\?", _userdata(_c8_inst(t))) is not None),
    _r("WaitCondition: Handle=!Ref handle, DependsOn instance, Timeout, Count 1", lambda t: any(
        U.ref_of(U.props(r).get("Handle")) in U.resources(t, "AWS::CloudFormation::WaitConditionHandle")
        and U.depends_on(r) == ["WebServer"] and int(str(U.props(r).get("Timeout"))) >= 60
        and int(str(U.props(r).get("Count"))) == 1
        for r in U.resources(t, "AWS::CloudFormation::WaitCondition").values())),
]

REQ_D1 = [
    _r("Security group has a port-80 ingress rule", lambda t: any(
        str(rule.get("FromPort")) == "80" for _, rule in U.sg_ingress_rules(t))),
    _r("Instance references the SG that exists", lambda t: all(
        U.ref_of(s) in U.resources(t, "AWS::EC2::SecurityGroup") for r in _insts(t).values()
        for s in (U.props(r).get("SecurityGroups") or [None])) and bool(_insts(t))),
    _r("KeyName uses the KeyPairName parameter", lambda t: all(
        U.ref_of(U.props(r).get("KeyName")) in (t.get("Parameters") or {}) for r in _insts(t).values())),
    _r("Output uses PublicIp", lambda t: _outputs_getatt(t, "PublicIp") >= 1),
]

REQ_D2 = [
    _r("Both subnets are inside the VPC CIDR", _subnets_inside_vpc),
    _r("Public subnet is really public (associated with a route table that routes to the IGW)",
       lambda t: bool(U.public_subnets(t))),
    _r("Private subnet routes 0.0.0.0/0 via the NAT (not the IGW)", lambda t: bool(U.private_subnets(t))),
    _r("NAT gateway lives in a public subnet", lambda t: bool(U.resources(t, "AWS::EC2::NatGateway")) and all(
        U.ref_of(U.props(r).get("SubnetId")) in U.public_subnets(t)
        for r in U.resources(t, "AWS::EC2::NatGateway").values())),
    _r("Instance uses SecurityGroupIds + !GetAtt GroupId (non-default VPC)", _sg_uses_ids),
    _r("The IGW route has DependsOn the attachment", lambda t: all(
        U.depends_on(r) for r in U.resources(t, "AWS::EC2::Route").values()
        if U.ref_of(U.props(r).get("GatewayId")) in U.resources(t, "AWS::EC2::InternetGateway"))),
]

REQ_D3 = [
    _r("Environment Default is one of its AllowedValues", lambda t: (lambda p: p.get("Default") in (
        p.get("AllowedValues") or []))(t.get("Parameters", {}).get("Environment") or {})),
    _r("The !If uses a condition that is defined", lambda t: all(
        (n["Fn::If"][0] in (t.get("Conditions") or {})) for n in U.walk(t.get("Resources"))
        if isinstance(n, dict) and "Fn::If" in n)),
    _r("BackupServer InstanceType refs an existing parameter", lambda t: U.ref_of(
        U.props(U.resources(t).get("BackupServer", {})).get("InstanceType")) in (t.get("Parameters") or {})),
    _r("FindInMap keys exist in the Mappings", lambda t: all(
        n["Fn::FindInMap"][2] in next(iter((t.get("Mappings") or {"x": {"y": {}}}).values())).get(
            "eu-west-1", {}) for n in U.walk(t.get("Resources")) if isinstance(n, dict) and "Fn::FindInMap" in n)),
    _r("Output of the conditional BackupServer has Condition: IsProd", lambda t: (
        (t.get("Outputs") or {}).get("BackupIp") or {}).get("Condition") == "IsProd"),
]

CHALLENGES = [
    dict(id="ec2-basic", kind="fill", level=1, title="Two EC2 instances + SSH security group",
         lab="Lab 4 (10-cf-ec2-student-template.yaml)", minutes=15, template=C1, reqs=REQ_C1,
         brief="Fill the blanks so both instances deploy into the default VPC with the SG attached.",
         bonus=["Parameters for KeyName + InstanceType (see ec2-params)", "Replace hard-coded AMI with SSM/Mapping",
                "Restrict SSH CIDR with a parameter", "Add Tags + Outputs with Descriptions"]),
    dict(id="ec2-params", kind="fill", level=1, title="Parameterise the EC2 template",
         lab="Lab 4 parameters (13-cf-ec2-student-parameters.yaml)", minutes=15, template=C2, reqs=REQ_C2,
         brief="Wire Parameters into the resources. Default must be a permitted value.",
         bonus=["AllowedPattern on a CIDR parameter", "Metadata Interface to group parameters",
                "Conditions: second instance only when Environment=prod"]),
    dict(id="vpc-public", kind="fill", level=2, title="VPC with a public subnet",
         lab="Lab 5 (18-1-vpc-basic.yaml)", minutes=20, template=C3, reqs=REQ_C3,
         brief="VPC, IGW + attachment, public subnet, route table, default route, association.",
         bonus=["Second public subnet in another AZ", "Parameters for the CIDRs", "Exports for VpcId/SubnetId"]),
    dict(id="vpc-nat", kind="fill", level=3, title="Public + private subnet with NAT gateway",
         lab="Lab 5 NAT (20-2-vpc-basic-inc-natgw.yaml)", minutes=25, template=C4, reqs=REQ_C4,
         brief="Add the NAT gateway (in the PUBLIC subnet) and the private route table.",
         bonus=["Private web server reachable only through the VPC", "Parameter to choose NAT on/off via Condition"]),
    dict(id="two-webservers", kind="fill", level=3, title="VPC + two public subnets + two web servers",
         lab="Lab 6 (22-5-final-combined-template.yaml)", minutes=30, template=C5, reqs=REQ_C5,
         brief="Second subnet, SG ids via GetAtt, per-instance DependsOn, outputs.",
         bonus=["Parameters for InstanceType/KeyName/AMI", "Application Load Balancer across both subnets",
                "Mapping or SSM AMI", "Restrict SSH + add SG-to-SG rule"]),
    dict(id="network-stack", kind="fill", level=3, title="Multi-stack: network stack with exports",
         lab="Lab 6 multi-stack (24-adam-network.yaml)", minutes=30, template=C6, reqs=REQ_C6,
         brief="Finish the network stack: CIDR, NAT wiring, SSH parameter, exports named <stack>-<Name>.",
         bonus=["Condition to skip NAT", "Second AZ", "Tags on everything"]),
    dict(id="servers-stack", kind="fill", level=3, title="Multi-stack: servers importing exports",
         lab="Lab 6 multi-stack (25-adam-servers.yaml)", minutes=20, template=C7, reqs=REQ_C7,
         prestack="network-stack",
         brief="Import the network stack's exports with Fn::ImportValue + Sub.",
         bonus=["Parameter for InstanceType with AllowedValues", "Condition for private server", "More outputs"]),
    dict(id="init-waitcondition", kind="fill", level=4, title="cfn-init + WaitCondition web server",
         lab="Lab 6 (28-waitcondition-init.yaml)", minutes=25, template=C8, reqs=REQ_C8,
         brief="Install Apache with AWS::CloudFormation::Init and make the stack wait for the signal.",
         bonus=["CreationPolicy instead of WaitCondition", "Add packages/services sections to Init",
                "Parameterise AMI via SSM", "Lock SSH to a parameter"]),
    dict(id="debug-typos", kind="debug", level=2, title="Debug drill 1: typos & syntax (cfn-lint catches these)",
         lab="debugging", minutes=10, template=D1, fixed=D1_FIXED, reqs=REQ_D1,
         brief="5 bugs. Read cfn-lint output, fix each. Practice reading the line numbers.", bonus=[]),
    dict(id="debug-logic", kind="debug", level=4, title="Debug drill 2: network logic bugs (lint only catches some)",
         lab="debugging", minutes=20, template=D2, fixed=D2_FIXED, reqs=REQ_D2,
         brief="Networking logic bugs that only show at deploy/runtime. Requirements list tells you what is broken.",
         bonus=[]),
    dict(id="debug-params", kind="debug", level=3, title="Debug drill 3: parameters, mappings, conditions",
         lab="debugging", minutes=15, template=D3, fixed=D3_FIXED, reqs=REQ_D3,
         brief="Defaults, conditions, FindInMap keys and conditional outputs.", bonus=[]),
]

BY_ID = {c["id"]: c for c in CHALLENGES}
