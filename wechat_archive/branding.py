"""Public product identity; persisted data and package identifiers stay compatible."""
APP_NAME = '思绪'
APP_NAME_EN = 'Sixu'

def window_title(language='zh_CN'):
    return APP_NAME_EN if language == 'en_US' else APP_NAME
