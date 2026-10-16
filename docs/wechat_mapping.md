# 微信模拟字段映射契约

输入为本工程定义的 **wechat-mock 1.0**，输出为 **chat-exchange 1.0**。这是一份虚构测试契约，不是对真实微信文件结构或字段语义的兼容声明。

## 输入整体结构

根对象必须有 format、format_version、account、contacts、messages。允许可选 timeUnit、metadata，不允许其他根字段。

- `format` 固定 `wechat-mock`，`format_version` 固定 `1.0`。
- `account` 有 wxid、nickname，可选 avatar；联系人也使用同样字段。
- wxid 与 nickname 为非空文字。contacts 的 wxid 不能重复，也不能与 account 重复。
- messages 每条必须含 msgId、talker、isSend、createTime、type、content，不接受其他字段。
- metadata 可选对象；原样转入标准来源元数据。

## 字段对应

| Mock 字段 | 标准字段 | 规则 |
|---|---|---|
| account.wxid | source.account_id、当前 User.id | 去掉首尾空白，作为当前查看账号 |
| account/contacts.wxid | User.id | 文件内用户引用 |
| account/contacts.wxid | User.external_id | `wechat-mock:<编码的账号 wxid>:<编码的用户 wxid>` |
| nickname | User.nickname | 通过公共文本校验，不凭昵称合并身份 |
| avatar | User.avatar | 可选标识或 null，不访问文件/网络 |
| msgId | Message.id、source_id | 整数转换为字符串，字符串保留；文件内应唯一 |
| createTime | Message.timestamp | Unix 整数，按明确秒/毫秒单位转换为 UTC 固定微秒 ISO |
| talker | 对方 User.id / external_id、Chat | 必须存在于 account 或 contacts |
| isSend | sender_id / receiver_id | 1 为账号→talker；0 为 talker→账号 |
| type | Message.type | mock 数字 1→text；文字类型保留；其他数字成为 unsupported-mock-type-N |
| content | Message.content | 保留原始空白、换行和 Unicode |
| metadata | source.metadata.original_metadata | 保留来源信息 |

账号及用户 wxid 使用 UTF-8 百分号编码后拼入外部标识，以避免冒号或特殊字符的边界歧义。mock 命名空间与真实来源隔离；更换 account.wxid 后，不会把同名联系人误合并到另一个账号。

## 方向与会话

```text
isSend = 1：sender = account.wxid，receiver = talker
isSend = 0：sender = talker，receiver = account.wxid
```

isSend 只能是整数 0 或 1，布尔值、字符串和其他数值会被拒绝，不猜测方向。

每个不同 talker 自动生成一个 private 会话，标准 Chat.id 为 `chat:<编码后的 talker>`，external_id 为 `private:<编码后的 talker>`，参与者为账号与 talker。talker 等于账号时生成单人私聊，兼容已有“给自己留记录”。

## 时间

根 timeUnit 默认为 seconds，可选 milliseconds。不得自动按位数猜测。createTime 接受整数或整数字符串，不接受浮点数、布尔值或普通日期文字。

```text
1767499200 seconds → 2026-01-04T04:00:00.000000Z → 北京时间 12:00
1767499200123 milliseconds → 2026-01-04T04:00:00.123000Z
```

毫秒转换使用整数除法，避免浮点精度损失。超出 Python 日期范围会明确提示检查 timeUnit。输出继续由原有 Validator 校验；不会修改系统时区。

## 消息类型与错误边界

mock 契约定义数字 1 为文字，这不保证真实微信所有版本使用相同表示。其他数字只保留未支持标记，不声称能识别图片、视频或文件子类型；原 Validator 会拒绝非 text。

错误的模拟格式标记、版本、方向、时间字段或联系人引用属于适配器映射错误：整份映射停止，Import Engine 保存 failed 报告，不写库。具体映射错误包含原始消息序号。

能够转换但超出当前能力的消息类型进入既有 Validator：默认跳过错误消息、导入其他合法记录，严格模式则整份拒绝。去重不使用新算法，仍按原引擎的双方 ID、UTC 时间和正文哈希判断。source_id 用于来源追溯，不代替去重键。
