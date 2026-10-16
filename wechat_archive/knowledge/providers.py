"""Explicit offline feature vectors or an already-installed loopback Ollama model."""

import hashlib
import http.client
import json
import math
import re
from urllib.parse import urlsplit

from ..errors import ConflictError, ValidationError


def unit_vector(values, dimensions=None):
    if (not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 8192
            or (dimensions is not None and len(values) != dimensions)
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)):
        raise ValidationError("模型返回的向量数量、维度或数值无效。")
    norm = math.hypot(*values)
    if not norm or not math.isfinite(norm):
        raise ValidationError("模型返回零向量或不可归一化的向量。")
    return [v/norm for v in values]


class LexicalEmbedding:
    """Deterministic local character features, not a learned semantic model."""

    def descriptor(self):
        return {"provider": "offline-lexical", "model": "char-hash-v1", "revision": "sha256-signed-1-2gram-v1",
                "dimensions": 256, "processing": "casefold-nonspace-1-2gram", "kind": "lexical", "local": True}

    def embed(self, texts):
        vectors = []
        for text in texts:
            chars = [c for c in text.casefold() if not c.isspace()]
            if not chars:
                chars = ["\0"]
            tokens = chars+["".join(chars[i:i+2]) for i in range(len(chars)-1)]
            values = [0.0]*256
            for token in tokens:
                hashed = hashlib.sha256(token.encode('utf-8')).digest()
                values[int.from_bytes(hashed[:2], 'big') % 256] += 1 if hashed[2]&1 else -1
            # Hash cancellation must not turn valid text into an invalid vector.
            if not any(values):
                values[0] = 1
            vectors.append(unit_vector(values, 256))
        return vectors


class OllamaEndpoint:
    """Never follows redirects, reads proxy configuration or downloads models."""

    def __init__(self, url="http://127.0.0.1:11434", timeout=90):
        try:
            parsed = urlsplit(url)
            if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                    or parsed.username or parsed.password or parsed.path not in ("", "/")
                    or parsed.query or parsed.fragment):
                raise ValueError()
            self.host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
            self.port = parsed.port or 11434
        except (ValueError, TypeError) as error:
            raise ValidationError("本地模型地址须为 http://127.0.0.1:端口（仅本机回环）。") from error
        if type(timeout) not in (int, float) or not 1 <= timeout <= 180:
            raise ValidationError("本地模型超时时间无效。")
        self.timeout = timeout

    def request(self, route, data=None):
        if route not in ("/api/tags", "/api/embed", "/api/chat"):
            raise ValidationError("未登记的本地模型操作。")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8') if data is not None else None
        if payload is not None and len(payload)>256000:
            raise ValidationError("本地模型输入超过预算。")
        try:
            connection.request("POST" if data is not None else "GET", route, body=payload,
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                raise ConflictError(f"本地模型服务返回 HTTP {response.status}；请检查已安装模型。")
            raw = response.read(4*1024*1024+1)
            if len(raw)>4*1024*1024:
                raise ConflictError("本地模型响应超过预算。")
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get("error"):
                raise ValueError()
            return result
        except (OSError, http.client.HTTPException) as error:
            raise ConflictError("无法连接本机 Ollama；请启动已有服务并检查地址。") from error
        except (ValueError, UnicodeError) as error:
            raise ConflictError("本地模型服务响应格式无效。") from error
        finally:
            connection.close()

    def models(self):
        rows = self.request("/api/tags").get("models")
        if not isinstance(rows, list) or len(rows)>1000:
            raise ConflictError("本地模型列表无效。")
        result = []
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("name"), str)
                    or not isinstance(row.get("digest"), str) or not re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", row["digest"])):
                raise ConflictError("模型缺少可核验的名称或版本摘要。")
            if row.get('remote_model') or row.get('remote_host') or 'cloud' in row['name'].casefold():
                continue
            result.append({"name": row["name"], "digest": row["digest"]})
        return result

    def model_revision(self, model):
        if not isinstance(model, str) or not model.strip() or len(model)>200 or any(ord(c)<32 for c in model):
            raise ValidationError("请先选择已有本地模型。")
        row = next((r for r in self.models() if r["name"] == model), None)
        if row is None:
            raise ConflictError("所选模型未安装；软件不会自动下载。")
        return row["digest"]


class OllamaEmbedding:
    def __init__(self, endpoint, model):
        self.endpoint = endpoint
        self.model = model
        self._descriptor = None

    def descriptor(self):
        revision = self.endpoint.model_revision(self.model)
        if self._descriptor is None:
            self.embed(["维度核验"])
        if self._descriptor['revision'] != revision:
            raise ConflictError("本地向量模型版本已变化，请重新选择模型并更新索引。")
        return dict(self._descriptor)

    def embed(self, texts):
        revision = self.endpoint.model_revision(self.model)
        result = self.endpoint.request("/api/embed", {"model": self.model, "input": texts, "truncate": False})
        vectors = result.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ValidationError("模型返回的向量批次不完整。")
        dimensions = self._descriptor['dimensions'] if self._descriptor else None
        normalized = [unit_vector(v, dimensions) for v in vectors]
        if normalized and any(len(v) != len(normalized[0]) for v in normalized):
            raise ValidationError("模型批次向量维度不一致。")
        if self._descriptor and revision != self._descriptor['revision']:
            raise ConflictError("本地向量模型已变化，本次操作未完成。")
        if normalized and self._descriptor is None:
            self._descriptor = {"provider": "ollama", "model": self.model, "revision": revision,
                                "dimensions": len(normalized[0]), "processing": "original-text-v1",
                                "kind": "semantic", "local": True,
                                "endpoint": f"http://{self.endpoint.host}:{self.endpoint.port}"}
        if self.endpoint.model_revision(self.model) != revision:
            raise ConflictError("生成向量时模型版本已变化。")
        return normalized
