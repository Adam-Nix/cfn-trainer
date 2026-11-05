"""Deploy a template into moto's in-memory fake AWS. Prints one JSON line. Run as a subprocess (has timeouts).
usage: moto_deploy.py <template.yaml> [prestack-template.yaml]"""
import json
import os
import sys

os.environ.update(AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x", AWS_DEFAULT_REGION="us-east-1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfnutil as U  # noqa: E402

SAMPLES = {"SSHLocation": "1.2.3.4/32", "KeyName": "vockey", "KeyPairName": "vockey"}


def params_for(text):
    t = U.load(text)
    out = []
    for name, p in (t.get("Parameters") or {}).items():
        if isinstance(p, dict) and "Default" not in p:
            out.append({"ParameterKey": name, "ParameterValue": SAMPLES.get(name, "sample")})
    return out


def main():
    from moto import mock_aws
    import boto3

    body = open(sys.argv[1]).read()
    pre = open(sys.argv[2]).read() if len(sys.argv) > 2 else None
    caps = ["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"]
    with mock_aws():
        cf = boto3.client("cloudformation", region_name="us-east-1")
        try:
            if pre:
                cf.create_stack(StackName="mark-network", TemplateBody=pre, Parameters=params_for(pre), Capabilities=caps)
            cf.create_stack(StackName="trainer", TemplateBody=body, Parameters=params_for(body), Capabilities=caps)
            st = cf.describe_stacks(StackName="trainer")["Stacks"][0]
            res = cf.describe_stack_resources(StackName="trainer")["StackResources"]
            print(json.dumps({"status": st["StackStatus"], "resources": len(res)}))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"status": "ERROR", "error": str(e)[:300]}))


main()
