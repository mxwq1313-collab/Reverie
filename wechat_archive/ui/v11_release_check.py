"""Frozen 1.1 diagnostics, with generated images and no account/model inference."""
from pathlib import Path
import json,subprocess


def verify_v11(app,folder):
    from PIL import Image
    import imageio_ffmpeg
    from ..agent.client import CONFIG
    from ..agent.tools import ArchiveTools
    from ..agent.evidence import evidence_packet
    from ..wechat_source.acquisition import _load_sdk
    from ..wechat_source.media_acquisition import local_media_reader
    panel=app.agent_panel
    panel._add('你','1.1自建问题');panel._add('Codex','1.1自建回答')
    assert panel.transcript.tag_cget('turn_user','justify')=='right'
    assert panel.transcript.tag_cget('turn_codex','justify')=='left'
    panel.active=True;panel._controls();app.root.update()
    assert panel.reply_indicator.get() and panel.reply_indicator_label.winfo_manager()
    panel.active=False;panel._controls();assert not panel.reply_indicator.get() and panel.reply_job is None
    packet=json.loads(evidence_packet(ArchiveTools(panel.current_scope())))['archive_evidence']
    assert packet['messages']['items'] and all(x['citation'] for x in packet['messages']['items'])
    assert 'code_mode_host = true' in CONFIG
    codec=Path(folder)/'codec';codec.mkdir()
    source=codec/'generated.hevc';ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    result=subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i','color=c=red:s=32x32','-frames:v','1','-c:v','libx265','-x265-params','pools=none:frame-threads=1','-f','hevc',str(source)],capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0,'Synthetic HEVC generation failed'
    container=b'wxgf'+source.read_bytes()
    class DB:account_dir=str(codec/'account')
    _load_sdk();reader=local_media_reader(DB(),codec/'assets')
    output=Path(reader._write_decrypted(container,'generated',str(codec/'assets')))
    assert output.suffix=='.jpg' and output.with_suffix('.wxgf').read_bytes()==container
    with Image.open(output) as image:assert image.size==(32,32)
    from .mbti_release_check import verify_mbti_ui
    return {'dialogue_alignment':True,'reply_indicator_lifecycle':True,'scoped_evidence_body':True,
            'bundled_hevc_decode':True,'original_wxgf_preserved':True,'interface_mbti':verify_mbti_ui(app),'real_inference':False}
