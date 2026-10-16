"""Human-readable account captions; selection remains bound to the native account."""
def account_labels(accounts):
    labels=[]
    for row in accounts:
        nickname=str(row.get('nickname') or row.get('nick_name') or row.get('self_nick') or '').strip()
        alias=str(row.get('weixin_id') or row.get('alias') or '').strip()
        identity=str(row.get('wxid') or row.get('account') or '')
        if nickname and alias:label=nickname+' · 微信号：'+alias
        elif alias:label='微信号：'+alias
        elif nickname:label=nickname+(' · 归档昵称' if row.get('identity_status')=='archive_label' else '')
        else:label='待登录核验 · '+identity
        labels.append(label)
    for i,label in enumerate(tuple(labels)):
        if labels.count(label)>1:
            duplicates=[j for j,value in enumerate(labels) if value==label]
            for j in duplicates:labels[j]+=' · '+str(accounts[j].get('wxid') or accounts[j]['account'])
    return labels
