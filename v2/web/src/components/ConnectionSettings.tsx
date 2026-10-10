import {useState} from 'react';
import {request, type Workspace} from '../types';
import {saveAccessCode} from '../accessCode';

export function ConnectionSettings({data, token, onToken, onConfigured, onClose}: {
  data: Workspace; token: string; onToken: (value: string) => void;
  onConfigured: () => void; onClose: () => void;
}) {
  const [key, setKey] = useState('');
  const [code, setCode] = useState(token);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function saveKey(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await request('/settings/openai', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({api_key: key.trim()})});
      setKey(''); onConfigured(); setNotice('서버에 API 키를 저장했습니다. AI 분석과 음성을 사용할 수 있습니다.');
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  function applyCode(value: string) {
    setError(''); setNotice('');
    try { saveAccessCode(value); onToken(value.trim()); setCode(value.trim()); setNotice(value.trim() ? '접근 코드를 저장했습니다.' : '저장된 접근 코드를 삭제했습니다.'); }
    catch { setError('브라우저 저장소를 사용할 수 없습니다. 사이트 저장소 설정을 확인하세요.'); }
  }

  return <>
    <p className="settings-copy">{data.meta.ai_configured ? '서버 AI가 연결되어 있습니다.' : 'AI 분석과 음성을 사용하려면 서버 API 키를 설정하세요.'}</p>
    {data.meta.local_dev_ai ? <form onSubmit={saveKey}>
      <p className="settings-copy">이 컴퓨터에서는 접근 코드 없이 연결됩니다. API 키는 서버에만 저장됩니다.</p>
      <label className="form-label">OpenAI API 키<input type="password" autoComplete="off" spellCheck={false} value={key} disabled={busy} onChange={event => setKey(event.target.value)} placeholder={data.meta.ai_configured ? '교체할 키 입력' : 'sk-…'}/></label>
      <div className="modal-actions"><button className="primary-button" disabled={busy || !key.trim()}>{busy ? '확인·저장 중…' : 'API 키 저장'}</button></div>
    </form> : <p className="settings-copy">API 키 설정은 서버 컴퓨터의 로컬 화면에서 가능합니다. 외부 접속은 관리자가 발급한 접근 코드를 입력하세요.</p>}
    {(!data.meta.local_dev_ai || token) && <section>
      <label className="form-label">AI 접근 코드<input type="password" autoComplete="off" value={code} onChange={event => setCode(event.target.value)}/></label>
      <p className="settings-copy">이 브라우저에 저장되어 다음 접속에도 사용됩니다. 공용 컴퓨터에서는 사용 후 삭제하세요.</p>
      <div className="modal-actions"><button className="secondary-button" onClick={() => applyCode('')}>접근 코드 삭제</button><button className="primary-button" onClick={() => applyCode(code)}>연결 적용</button></div>
    </section>}
    {error && <p className="voice-error" role="alert">{error}</p>}
    {notice && <p className="settings-copy" role="status">{notice}</p>}
    <div className="modal-actions"><button className="secondary-button" disabled={busy} onClick={onClose}>닫기</button></div>
  </>;
}
