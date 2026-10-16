"""有界 Protobuf wire 投影探测；结构兼容不代表 Schema 已确认。"""

import base64
import hashlib


class WireProbeError(ValueError):
    pass


class WireLimitError(WireProbeError):
    pass


def text_shape(data):
    try:
        value = data.decode("utf-8")
    except UnicodeError:
        return {"utf8":False}
    printable = sum(c.isprintable() or c in '\r\n\t' for c in value)
    result = {"utf8":True, "characters":len(value), "printable_fraction":round(printable/max(1,len(value)),4),
              "raw_text_exported":False, "sha256":hashlib.sha256(data).hexdigest()}
    if value.startswith('_wxroam:'):
        result['shape'] = 'wxroam_prefixed_token'
        try:
            decoded = base64.b64decode(value.split(':',1)[1],validate=True)
            result['base64_decoded_bytes'] = len(decoded)
        except (ValueError, base64.binascii.Error):
            result['base64_decoded_bytes'] = None
        result['key_role'] = 'unverified'
    else:
        result['shape'] = 'text_candidate' if printable/max(1,len(value)) >= .95 else 'binary_compatible_utf8'
    return result


def _varint(data, position):
    value = 0
    for index in range(10):
        if position >= len(data):
            raise WireProbeError('截断 varint')
        byte = data[position]
        position += 1
        if index == 9 and byte > 1:
            raise WireProbeError('varint 超过 64 位')
        value |= (byte & 127) << (7*index)
        if byte < 128:
            if index and byte == 0:
                raise WireProbeError('非最短 varint 不在本次探测投影内')
            return value, position
    raise WireProbeError('未终止 varint')


def parse_wire(data, *, max_fields=256, max_depth=2):
    if not isinstance(data, bytes) or not data:
        raise WireProbeError('空数据不能作为 wire 格式证据')
    if len(data) > 65536 or type(max_fields) is not int or not 1 <= max_fields <= 1024 or type(max_depth) is not int or not 0 <= max_depth <= 4:
        raise WireProbeError('wire 探测超过大小/字段/深度限制')
    nodes = [0]
    def parse(body, depth):
        position, fields = 0, []
        while position < len(body):
            nodes[0] += 1
            if nodes[0] > max_fields:
                raise WireLimitError('字段数量超过限制')
            start = position
            tag, position = _varint(body, position)
            number, wire = tag >> 3, tag & 7
            if not 1 <= number < 2**29 or wire not in (0,1,2,5):
                raise WireProbeError('未知/不支持的字段号或 wire type（不处理 group）')
            row = {"offset":start,"field_number":number,"wire_type":wire,"meaning":"unverified"}
            if wire == 0:
                row['unsigned_value'],position = _varint(body,position)
            else:
                length = 8 if wire == 1 else 4 if wire == 5 else None
                if wire == 2:
                    length,position = _varint(body,position)
                if length > len(body)-position:
                    raise WireProbeError('字段长度超出剩余数据')
                value = body[position:position+length]
                row.update(value_offset=position,value_bytes=length,value_sha256=hashlib.sha256(value).hexdigest())
                position += length
                if wire == 2:
                    row['text_shape'] = text_shape(value)
                    if value and depth < max_depth:
                        try:
                            nested = parse(value,depth+1)
                        except WireLimitError:
                            raise
                        except WireProbeError:
                            row['nested_wire_compatible'] = False
                        else:
                            row['nested_wire_compatible'] = True
                            row['nested_fields'] = nested
            row['encoded_bytes'] = position-start
            fields.append(row)
        return fields
    fields = parse(data,0)
    return {"compatible":True,"projection":"protobuf-wire-0-1-2-5","consumed_bytes":len(data),
            "schema_verified":False,"fields":fields,"raw_bytes_exported":False}


def probe_wire(data, *, complete=True):
    if not complete:
        return {"compatible":False,"schema_verified":False,"reason":"采样不完整，不认证整段 wire 结构"}
    try:
        return parse_wire(data)
    except WireProbeError as exc:
        return {"compatible":False,"schema_verified":False,"reason":str(exc)}
