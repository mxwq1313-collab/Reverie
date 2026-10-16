"""只从登记映射读取指定列，不访问图片/语音资源。"""


class AndroidExtractor:
    def __init__(self, reader, profile, projected):
        self.reader, self.profile, self.projected = reader, profile, projected

    def _rows(self, entity):
        fields = self.projected[entity]
        mapping = self.profile[entity]
        for row in self.reader.iter_rows(mapping["table"], list(fields.values()), order_by=fields["id"]):
            yield {logical: row[column] for logical, column in fields.items()}

    def contacts(self):
        return self._rows("contacts")

    def messages(self):
        return self._rows("messages")
