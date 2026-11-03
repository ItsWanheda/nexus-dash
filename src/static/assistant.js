/* NEXUS Sentinel local diagnostic assistant UI. No cloud requests or command execution. */
(function (global) {
  'use strict';
  const transcript=[];
  let models=[];
  let configuredModel='qwen3.5:4b';
  let pendingQuestion='';
  let busy=false;
  function el(id){return document.getElementById(id);}
  function esc(value){return String(value==null?'':value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'","&#39;");}
  function setStatus(message){const target=el('sentinel-status');if(target)target.textContent=message;}
  function renderMessages(){
    const target=el('sentinel-messages');if(!target)return;
    if(!transcript.length){
      target.innerHTML='<div class="sentinel-welcome"><span class="sentinel-symbol">✧</span><h3>What is happening on your machine?</h3><p>Describe a symptom, ask a technical question, or ask Sentinel to explain recent NEXUS evidence. It can only read the context you choose to include; it cannot run commands or change your PC.</p><div class="sentinel-suggestions"><button type="button" data-action="sentinel-prompt" data-prompt="My computer feels slow. Help me identify which evidence I should check first.">My PC feels slow</button><button type="button" data-action="sentinel-prompt" data-prompt="Explain CPU, RAM, disk and network pressure in simple terms and tell me how to investigate them.">Explain resource pressure</button><button type="button" data-action="sentinel-prompt" data-prompt="How can I safely investigate an application that freezes or crashes?">App freezes or crashes</button></div></div>';
      return;
    }
    target.replaceChildren();
    transcript.forEach(item=>{
      const row=document.createElement('article');
      row.className='sentinel-message sentinel-'+item.role;
      const label=document.createElement('span');label.className='eyebrow';label.textContent=item.role==='user'?'YOU':'NEXUS SENTINEL';
      const content=document.createElement('div');content.className='sentinel-message-content';content.textContent=item.content;
      row.appendChild(label);row.appendChild(content);
      if(item.meta){const meta=document.createElement('small');meta.className='muted';meta.textContent=item.meta;row.appendChild(meta);}
      target.appendChild(row);
    });
    target.scrollTop=target.scrollHeight;
  }
  async function loadStatus(){
    const status=el('sentinel-status'),selector=el('sentinel-model');
    if(!status||!selector)return;
    status.textContent='CHECKING LOCAL MODEL…';
    try{
      const result=await api('/assistant/status');
      models=Array.isArray(result.models)?result.models:[];
      configuredModel=result.configured_model||result.recommended_model||configuredModel;
      selector.innerHTML=models.length
        ? models.map(name=>'<option value="'+esc(name)+'">'+esc(name)+'</option>').join('')
        : '<option value="'+esc(configuredModel)+'">Not installed: '+esc(configuredModel)+'</option>';
      selector.value=models.includes(configuredModel)?configuredModel:(result.recommended_model||configuredModel);
      status.textContent=result.status==='ready'?'LOCAL MODEL READY · '+(result.provider||'OLLAMA'):
        result.status==='no-models'?'OLLAMA READY · NO MODELS INSTALLED':'BUILT-IN GUIDE · OLLAMA OFFLINE';
      status.className='panel-tag '+(result.status==='ready'?'sentinel-ready':'');
      const hint=el('sentinel-model-help');
      if(hint)hint.textContent=result.status==='ready'
        ? 'Model runs locally. No chat messages are sent to a cloud service.'
        : 'Install Ollama and pull a model locally. NEXUS never downloads a model automatically; the built-in guide remains available.';
    }catch(error){
      status.textContent='BUILT-IN GUIDE · LOCAL MODEL UNAVAILABLE';
      if(el('sentinel-model-help'))el('sentinel-model-help').textContent=error.message;
    }
  }
  async function saveModel(){
    const selector=el('sentinel-model');if(!selector)return;
    const model=selector.value;
    if(!model||!models.includes(model))return;
    try{
      await api('/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({assistant_model:model})});
      configuredModel=model;
    }catch(error){setStatus('Could not save model preference: '+error.message);}
  }
  async function sendMessage(forcedText){
    if(busy)return;
    const input=el('sentinel-input');
    const message=String(forcedText!==undefined?forcedText:(input?input.value:'')).trim();
    if(!message)return;
    if(message.length>2000){setStatus('Message is too long (2,000 characters maximum).');return;}
    if(input)input.value='';
    const history=transcript.slice(-8).map(item=>({role:item.role,content:item.content}));
    transcript.push({role:'user',content:message});
    renderMessages();
    busy=true;
    const send=el('sentinel-send');if(send)send.disabled=true;
    setStatus('NEXUS SENTINEL IS THINKING…');
    try{
      const model=el('sentinel-model')?el('sentinel-model').value:configuredModel;
      const includeContext=Boolean(el('sentinel-context')&&el('sentinel-context').checked);
      const response=await api('/assistant/chat',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message,model,history,include_context:includeContext})
      });
      transcript.push({
        role:'assistant',content:String(response.content||'No answer was returned.'),
        meta:(response.mode==='local-model'?'Local model: '+response.model:'Built-in diagnostic guide')+
          (response.context_included?' · NEXUS telemetry included':' · no telemetry context')
      });
      setStatus(response.status==='ready'?'LOCAL MODEL RESPONSE':'BUILT-IN FALLBACK RESPONSE');
    }catch(error){
      transcript.push({role:'assistant',content:'I could not contact the local assistant endpoint: '+error.message,
        meta:'No cloud fallback was attempted.'});
      setStatus('LOCAL ASSISTANT REQUEST FAILED');
    }finally{
      busy=false;if(send)send.disabled=false;renderMessages();if(input)input.focus();
    }
  }
  function render(main){
    main.innerHTML=
      '<section class="page-intro"><div><div class="eyebrow">LOCAL AI / PRIVATE DIAGNOSTIC COMPANION</div><h2>NEXUS Sentinel</h2><p>A small local language model that explains system behaviour, interprets evidence and guides safe troubleshooting. It does not have command-execution tools.</p></div><button class="secondary-button" type="button" data-action="sentinel-refresh">↻ Check local model</button></section>'+
      '<section class="panel sentinel-status-bar"><div><span class="eyebrow">INFERENCE PROVIDER</span><strong id="sentinel-status">CHECKING LOCAL MODEL…</strong><p id="sentinel-model-help" class="muted">Checking Ollama at 127.0.0.1:11434.</p></div><label>Installed model<select id="sentinel-model" class="flight-select"><option>Checking…</option></select></label></section>'+
      '<section class="panel sentinel-chat-panel"><div class="sentinel-chat-toolbar"><label><input type="checkbox" id="sentinel-context" checked> Include current NEXUS evidence (metrics, anomalies, recent processes and local incidents)</label><button class="text-button" type="button" data-action="sentinel-clear">Clear conversation</button></div><div id="sentinel-messages" class="sentinel-messages"></div><div class="sentinel-compose"><textarea id="sentinel-input" rows="3" maxlength="2000" placeholder="Describe the issue or ask a question… (Ctrl+Enter to send)"></textarea><button id="sentinel-send" class="primary-button" type="button" data-action="sentinel-send">Ask Sentinel</button></div><p class="table-note">Only Ollama models already installed on this computer are available. NEXUS never pulls a model automatically, never contacts a cloud inference endpoint, and never executes commands. The context toggle is optional.</p></section>';
    renderMessages();loadStatus();
    if(pendingQuestion){const text=pendingQuestion;pendingQuestion='';sendMessage(text);}
  }
  function handleAction(action,target){
    if(action==='sentinel-send'){sendMessage();return true;}
    if(action==='sentinel-clear'){transcript.length=0;renderMessages();setStatus('CONVERSATION CLEARED');return true;}
    if(action==='sentinel-refresh'){loadStatus();return true;}
    if(action==='sentinel-prompt'){sendMessage(target&&target.dataset.prompt?target.dataset.prompt:'');return true;}
    return false;
  }
  function handleChange(target){if(target&&target.id==='sentinel-model')saveModel();}
  function openWithQuestion(question){
    pendingQuestion=String(question||'Please help me troubleshoot my computer.').slice(0,1800);
    if(state.tab==='assistant'){const text=pendingQuestion;pendingQuestion='';sendMessage(text);return;}
    switchTab('assistant');
  }
  function afterRender(){}
  global.NexusAssistant={render,handleAction,handleChange,openWithQuestion,afterRender};
})(window);
