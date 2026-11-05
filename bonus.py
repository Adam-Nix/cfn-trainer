"""Heuristic 'extra complexity' scorer. This is MY checklist of things that usually look good in an
IaC practical - it is NOT your lecturer's rubric. Use it to decide what to add after the base works."""
import re

import cfnutil as U

TAGGABLE = {
    "AWS::EC2::Instance", "AWS::EC2::VPC", "AWS::EC2::Subnet", "AWS::EC2::SecurityGroup",
    "AWS::EC2::InternetGateway", "AWS::EC2::RouteTable", "AWS::EC2::NatGateway",
}


def _params(t):
    p = t.get("Parameters")
    return p if isinstance(p, dict) else {}


def _used(t, fn_name):
    return any(isinstance(n, dict) and fn_name in n for n in U.walk(t.get("Resources")))


def f_params(t, lint):
    return bool(_params(t))


def f_constraints(t, lint):
    keys = {"AllowedValues", "AllowedPattern", "MinLength", "MaxLength", "MinValue", "MaxValue"}
    return any(isinstance(v, dict) and keys & set(v) for v in _params(t).values())


def f_special_type(t, lint):
    return any(isinstance(v, dict) and str(v.get("Type", "")).startswith("AWS::") for v in _params(t).values())


def f_mappings(t, lint):
    return bool(t.get("Mappings")) and _used(t, "Fn::FindInMap")


def f_conditions(t, lint):
    if not t.get("Conditions"):
        return False
    if _used(t, "Fn::If"):
        return True
    return any("Condition" in r for r in U.resources(t).values())


def f_rules(t, lint):
    return bool(t.get("Rules"))


def f_interface(t, lint):
    m = t.get("Metadata")
    return isinstance(m, dict) and "AWS::CloudFormation::Interface" in m


def f_outputs(t, lint):
    o = t.get("Outputs")
    return isinstance(o, dict) and len(o) >= 3 and all(isinstance(v, dict) and v.get("Description") for v in o.values())


def f_exports(t, lint):
    o = t.get("Outputs")
    return isinstance(o, dict) and any(isinstance(v, dict) and "Export" in v for v in o.values())


def f_tags(t, lint):
    rs = [r for r in U.resources(t).values() if r.get("Type") in TAGGABLE]
    if not rs:
        return False
    tagged = [r for r in rs if U.props(r).get("Tags")]
    return len(tagged) / len(rs) >= 0.8


def f_deletion(t, lint):
    return any("DeletionPolicy" in r or "UpdateReplacePolicy" in r for r in U.resources(t).values())


def f_multi_az(t, lint):
    azs = set()
    for r in U.resources(t, "AWS::EC2::Subnet").values():
        az = U.props(r).get("AvailabilityZone")
        azs.add(repr(az))
    return len(azs) >= 2


def f_private_nat(t, lint):
    return bool(U.private_subnets(t)) and bool(U.resources(t, "AWS::EC2::NatGateway"))


def f_least_priv(t, lint):
    """No rule exposes SSH, all traffic, or a wide port range to the whole internet."""
    seen = False
    for _, rule in U.sg_ingress_rules(t):
        seen = True
        if str(rule.get("CidrIp")) != "0.0.0.0/0" and str(rule.get("CidrIpv6")) != "::/0":
            continue
        if str(rule.get("IpProtocol")) in ("-1", "all"):
            return False
        try:
            lo, hi = int(str(rule.get("FromPort"))), int(str(rule.get("ToPort")))
        except ValueError:
            continue
        if lo <= 22 <= hi or hi - lo > 10:
            return False
    return seen


def f_sg_to_sg(t, lint):
    return any(
        "SourceSecurityGroupId" in rule for _, rule in U.sg_ingress_rules(t)
    )


def f_iam(t, lint):
    return bool(U.resources(t, "AWS::IAM::Role")) and bool(U.resources(t, "AWS::IAM::InstanceProfile"))


def f_dynamic_ami(t, lint):
    txt = repr(t)
    if "resolve:ssm" in txt or "AWS::SSM::Parameter::Value" in txt:
        return True
    return any(isinstance(U.props(r).get("ImageId"), dict) and "Fn::FindInMap" in U.props(r)["ImageId"]
               for r in U.resources(t, "AWS::EC2::Instance").values())


def f_init_wait(t, lint):
    types = {r.get("Type") for r in U.resources(t).values()}
    has_init = any(isinstance(r.get("Metadata"), dict) and "AWS::CloudFormation::Init" in r["Metadata"]
                   for r in U.resources(t).values())
    return has_init or "AWS::CloudFormation::WaitCondition" in types or any(
        "CreationPolicy" in r for r in U.resources(t).values())


def f_depends(t, lint):
    return any("DependsOn" in r for r in U.resources(t).values())


def f_extra(t, lint):
    extra = {"AWS::ElasticLoadBalancingV2::LoadBalancer", "AWS::AutoScaling::AutoScalingGroup",
             "AWS::S3::Bucket", "AWS::CloudWatch::Alarm", "AWS::SNS::Topic", "AWS::RDS::DBInstance",
             "AWS::EC2::LaunchTemplate", "AWS::Logs::LogGroup"}
    return bool(extra & {r.get("Type") for r in U.resources(t).values()})


def f_lint_clean(t, lint):
    return lint is not None and lint.get("errors", 1) == 0 and lint.get("warnings", 1) == 0


def f_description(t, lint):
    return bool(t.get("Description"))


# (key, label, weight, effort 1-3, snippet name, check)
FEATURES = [
    ("params", "Parameters (KeyName, InstanceType, CIDRs...)", 6, 1, "params", f_params),
    ("constraints", "Parameter constraints (AllowedValues/Pattern)", 6, 1, "constraints", f_constraints),
    ("special_type", "AWS-specific parameter type (KeyPair/SSM)", 4, 1, "params", f_special_type),
    ("mappings", "Mappings + FindInMap", 6, 2, "mappings", f_mappings),
    ("conditions", "Conditions used (Fn::If or Condition:)", 8, 2, "conditions", f_conditions),
    ("rules", "Rules section", 3, 2, "rules", f_rules),
    ("interface", "Metadata Interface (parameter groups)", 3, 1, "interface", f_interface),
    ("outputs", "3+ Outputs, each with a Description", 5, 1, "outputs", f_outputs),
    ("exports", "Output Export (cross-stack)", 4, 1, "outputs", f_exports),
    ("tags", "Tags on (nearly) every taggable resource", 6, 1, "tags", f_tags),
    ("deletion", "DeletionPolicy / UpdateReplacePolicy", 3, 1, "deletion", f_deletion),
    ("multi_az", "Subnets in 2+ AZs", 5, 1, "multi-az", f_multi_az),
    ("private_nat", "Private subnet + NAT gateway", 6, 3, "nat", f_private_nat),
    ("least_priv", "No SSH open to 0.0.0.0/0 (use a parameter)", 5, 1, "ssh-param", f_least_priv),
    ("sg_to_sg", "SG-to-SG rule (SourceSecurityGroupId)", 3, 2, "sg-to-sg", f_sg_to_sg),
    ("iam", "IAM Role + InstanceProfile (often blocked in Learner Lab)", 2, 3, "iam", f_iam),
    ("dynamic_ami", "AMI not hard-coded (SSM or Mapping)", 4, 1, "ssm-ami", f_dynamic_ami),
    ("init_wait", "cfn-init / WaitCondition / CreationPolicy", 5, 3, "init-wait", f_init_wait),
    ("depends", "Explicit DependsOn where order matters", 3, 1, "depends", f_depends),
    ("extra", "Extra service (S3, Alarm, ALB, ASG, SNS...)", 5, 3, "extra", f_extra),
    ("lint_clean", "cfn-lint: zero errors AND zero warnings", 4, 2, None, f_lint_clean),
    ("description", "Template Description", 1, 1, None, f_description),
]


def score(t, lint=None):
    got, missing, total = 0, [], 0
    for key, label, w, effort, snip, fn in FEATURES:
        total += w
        try:
            ok = bool(fn(t, lint))
        except Exception:
            ok = False
        if ok:
            got += w
        else:
            missing.append((w / effort, w, effort, label, snip))
    missing.sort(reverse=True)
    return got, total, missing
