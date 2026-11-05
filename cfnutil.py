"""CloudFormation YAML helpers: loader that understands !Ref/!GetAtt/etc. plus template inspection."""
import ipaddress
import re

import yaml


class _Loader(yaml.SafeLoader):
    pass


def _construct(loader, suffix, node):
    name = suffix if suffix in ("Ref", "Condition") else "Fn::" + suffix
    if isinstance(node, yaml.ScalarNode):
        val = loader.construct_scalar(node)
        if suffix == "GetAtt":
            val = val.split(".", 1)
    elif isinstance(node, yaml.SequenceNode):
        val = loader.construct_sequence(node, deep=True)
    else:
        val = loader.construct_mapping(node, deep=True)
    return {name: val}


_Loader.add_multi_constructor("!", _construct)


def load(text):
    data = yaml.load(text, Loader=_Loader)
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------- inspection

def resources(t, typ=None):
    out = {}
    for k, v in (t.get("Resources") or {}).items():
        if isinstance(v, dict) and (typ is None or v.get("Type") == typ):
            out[k] = v
    return out


def props(r):
    p = r.get("Properties")
    return p if isinstance(p, dict) else {}


def walk(v):
    yield v
    if isinstance(v, dict):
        for x in v.values():
            yield from walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from walk(x)


def ref_of(v):
    return v.get("Ref") if isinstance(v, dict) and "Ref" in v else None


def getatt_of(v):
    """('Logical', 'Attr') for a GetAtt node, else None."""
    if isinstance(v, dict) and "Fn::GetAtt" in v:
        g = v["Fn::GetAtt"]
        if isinstance(g, str):
            g = g.split(".", 1)
        if isinstance(g, list) and len(g) == 2:
            return (g[0], g[1])
    return None


def mentions(v, logical):
    """True if value references logical id via Ref, GetAtt or ${Sub}."""
    for n in walk(v):
        if ref_of(n) == logical:
            return True
        ga = getatt_of(n)
        if ga and ga[0] == logical:
            return True
        if isinstance(n, dict) and "Fn::Sub" in n:
            s = n["Fn::Sub"]
            s = s[0] if isinstance(s, list) and s else s
            if isinstance(s, str) and re.search(r"\$\{" + re.escape(logical) + r"[.}]", s):
                return True
    return False


def depends_on(r):
    d = r.get("DependsOn")
    if d is None:
        return []
    return [d] if isinstance(d, str) else list(d)


def net(v):
    try:
        return ipaddress.ip_network(v, strict=False)
    except (ValueError, TypeError):
        return None


def flat_text(v):
    return "\n".join(x for x in walk(v) if isinstance(x, str))


# --------------------------------------------------------------- network model

def route_tables(t):
    """{rt_logical: {'igw': bool, 'nat': bool}} based on AWS::EC2::Route resources."""
    igws = set(resources(t, "AWS::EC2::InternetGateway"))
    rts = {k: {"igw": False, "nat": False} for k in resources(t, "AWS::EC2::RouteTable")}
    for r in resources(t, "AWS::EC2::Route").values():
        p = props(r)
        rt = ref_of(p.get("RouteTableId"))
        if rt not in rts:
            continue
        if str(p.get("DestinationCidrBlock")) != "0.0.0.0/0":
            continue
        if ref_of(p.get("GatewayId")) in igws:
            rts[rt]["igw"] = True
        if p.get("NatGatewayId") is not None:
            rts[rt]["nat"] = True
    return rts


def subnet_rt(t):
    out = {}
    for r in resources(t, "AWS::EC2::SubnetRouteTableAssociation").values():
        p = props(r)
        s, rt = ref_of(p.get("SubnetId")), ref_of(p.get("RouteTableId"))
        if s and rt:
            out[s] = rt
    return out


def public_subnets(t):
    rts = route_tables(t)
    return {s for s, rt in subnet_rt(t).items() if rts.get(rt, {}).get("igw")}


def private_subnets(t):
    rts = route_tables(t)
    return {s for s, rt in subnet_rt(t).items() if rts.get(rt, {}).get("nat")}


def sg_ingress_rules(t):
    """Yield (sg_logical, rule_dict) for inline ingress and standalone SecurityGroupIngress."""
    for k, r in resources(t, "AWS::EC2::SecurityGroup").items():
        rules = props(r).get("SecurityGroupIngress") or []
        for rule in rules if isinstance(rules, list) else []:
            if isinstance(rule, dict):
                yield k, rule
    for k, r in resources(t, "AWS::EC2::SecurityGroupIngress").items():
        yield ref_of(props(r).get("GroupId")) or (getatt_of(props(r).get("GroupId")) or ("?",))[0], props(r)
