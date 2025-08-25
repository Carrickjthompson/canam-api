<!-- CAN-AM VOICE ASSISTANT (branded stripe + footer, STOP button, CA voice, speech-only pronunciation fix) -->
<div class="canam-widget">
  <div class="cw-wrap">
    <header class="cw-header">
      <img class="cw-logo"
           src="https://static1.squarespace.com/static/67f2bca628a1eb007014a1f7/t/68ab7e788b82127a2c06edd8/1756069496767/Can-Am-logo.jpg"
           alt="Can-Am Logo">
      <div class="cw-stripe"></div>
    </header>

    <main class="cw-main">
      <h1 class="cw-title">Can-Am 3-Wheel Assistant</h1>
      <p class="cw-sub">Tap the button, ask your question, hear the answer.</p>

      <div class="cw-cta">
        <button id="cw-btn" class="cw-btn" aria-pressed="false">
          <span class="cw-dot" aria-hidden="true"></span>
          Ask Now
        </button>
        <button id="cw-stop" class="cw-stop" hidden aria-label="Stop speaking">Stop</button>
      </div>

      <div id="cw-out" class="cw-out" role="status" aria-live="polite"></div>
      <div id="cw-hint" class="cw-hint"></div>
    </main>

    <footer class="cw-footer">
      <a href="https://can-am.brp.com/on-road/us/en/models/3-wheel-vehicles.html"
         target="_blank" rel="noopener" class="cw-link">Explore Official Can-Am Models</a>
      <p class="cw-legal">© BRP | All rights reserved</p>
    </footer>
  </div>
</div>

<style>
  .canam-widget{
    display:flex;justify-content:center;align-items:center;
    padding:12px 16px;min-height:90vh;background:#f5f5f5;
  }
  .canam-widget .cw-wrap{
    width:100%;max-width:560px;margin:0 auto;border-radius:12px;
    box-shadow:0 10px 32px rgba(0,0,0,.15);overflow:hidden;background:#fff;
    display:flex;flex-direction:column;
  }
  .canam-widget .cw-header{text-align:center;padding:14px 10px 0}
  .canam-widget .cw-logo{display:block;width:100%;max-width:320px;margin:0 auto 6px}
  .canam-widget .cw-stripe{width:100%;height:8px;background:linear-gradient(to right,#E2231A 50%,#FFCC00 50%)}

  .canam-widget .cw-main{text-align:center;padding:18px 14px;flex:1}
  .canam-widget .cw-title{margin:8px 0 6px;font-size:clamp(18px,4.5vw,26px)}
  .canam-widget .cw-sub{margin:0 0 16px;color:#444}
  .canam-widget .cw-cta{display:flex;gap:.6rem;justify-content:center;align-items:center}

  .canam-widget .cw-btn{
    display:inline-flex;align-items:center;gap:.6rem;justify-content:center;
    padding:14px 20px;border-radius:999px;border:0;cursor:pointer;
    background:#000;color:#fff;font-size:clamp(16px,4vw,18px);font-weight:700;
    box-shadow:0 6px 18px rgba(0,0,0,.25);
  }
  .canam-widget .cw-dot{
    width:10px;height:10px;border-radius:50%;
    background:#FFCC00;box-shadow:0 0 0 0 rgba(226,35,26,.7);
    animation:cw-pulse 1.6s infinite;
  }
  @keyframes cw-pulse{
    0%{box-shadow:0 0 0 0 rgba(226,35,26,.7)}
    70%{box-shadow:0 0 0 12px rgba(226,35,26,0)}
    100%{box-shadow:0 0 0 0 rgba(226,35,26,0)}
  }

  .canam-widget .cw-stop{
    padding:14px 20px;border-radius:999px;border:0;cursor:pointer;
    background:#E2231A;color:#fff;font-size:clamp(16px,4vw,18px);font-weight:700;
    box-shadow:0 6px 18px rgba(0,0,0,.25);
  }
  .canam-widget .cw-stop[hidden]{display:none}

  .canam-widget .cw-out{
    margin:16px auto 0;max-width:520px;min-height:28px;
    padding:14px;border-radius:10px;background:#fff6e6;
    border:1px solid rgba(0,0,0,.08);text-align:left;white-space:pre-wrap
  }
  .canam-widget .cw-out h1,.canam-widget .cw-out h2,.canam-widget .cw-out h3{margin:.4rem 0;color:#E2231A}
  .canam-widget .cw-out ul{padding-left:1.1rem;margin:.4rem 0}
  .canam-widget .cw-out li{margin:.15rem 0}
  .canam-widget .cw-hint{margin-top:10px;font-size:13px;color:#777;text-align:center}

  .canam-widget .cw-footer{text-align:center;padding:16px;background:#fff;border-top:1px solid #eee}
  .canam-widget .cw-link{
    display:inline-block;padding:12px 20px;border-radius:6px;
    background:#000;color:#fff;font-weight:700;text-decoration:none;
    box-shadow:0 4px 12px rgba(0,0,0,.2);margin-bottom:8px;
  }
  .canam-widget .cw-link:hover{opacity:.85}
  .canam-widget .cw-legal{font-size:12px;color:#555;margin:0}

  @media (max-width:480px){
    .canam-widget{padding:8px}
    .canam-widget .cw-main{padding:16px 12px}
  }
</style>

<script>
document.addEventListener("DOMContentLoaded", () => {
  const API = "https://web-production-4105a.up.railway.app"; // your Railway API (unchanged)
  const btn    = document.getElementById("cw-btn");
  const stopBtn= document.getElementById("cw-stop");
  const out    = document.getElementById("cw-out");
  const hint   = document.getElementById("cw-hint");

  let currentUtterance = null;

  // Simple Markdown -> HTML cleaner (keeps things tidy)
  function formatMarkdown(text){
    return text
      .replace(/^### (.*$)/gim, "<h3>$1</h3>")
      .replace(/^## (.*$)/gim,  "<h2>$1</h2>")
      .replace(/^# (.*$)/gim,   "<h1>$1</h1>")
      .replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>")
      .replace(/^- (.*$)/gim, "<ul><li>$1</li></ul>")
      .replace(/\n{2,}/g, "<br><br>");
  }

  // Canadian voice if available; fallback to any English voice
  function speak(text){
    try{
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      const voices = speechSynthesis.getVoices();
      const ca = voices.find(v => /en-CA/i.test(v.lang)) || voices.find(v => /English/i.test(v.name));
      if (ca) u.voice = ca;
      u.lang = "en-CA";
      u.rate = 1.0;
      u.pitch = 1.0;
      currentUtterance = u;
      speechSynthesis.speak(u);
      stopBtn.hidden = false;
      u.onend = () => { stopBtn.hidden = true; currentUtterance = null; };
    }catch(e){ console.error("Speech error:", e); }
  }

  stopBtn.addEventListener("click", () => {
    speechSynthesis.cancel();
    stopBtn.hidden = true;
    currentUtterance = null;
  });

  async function askChat(text){
    const r = await fetch(API + "/chat", {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ question: text })
    });
    if(!r.ok) throw new Error("HTTP "+r.status);
    const data = await r.json();
    return data.answer || "No answer.";
  }

  btn.addEventListener("click", () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if(!SR){ out.innerHTML = "Use Chrome/Edge/Safari for voice."; return; }

    const rec = new SR();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.start();
    out.innerHTML = "Listening…";

    rec.onresult = async (e) => {
      const q = e.results[0][0].transcript;
      out.innerHTML = "You: " + q + "<br>Thinking…";
      try{
        const a = await askChat(q);

        // Render exact GPT answer (cleaned for display)
        out.innerHTML = formatMarkdown(a);

        // Speech-only tweaks (do NOT change what’s displayed)
        const speakOnly = a
          .replace(/sea[\-\s]*to[\-\s]*sky/gi, "See to Sky") // pronunciation fix
          .replace(/[#*`>_]/g, ""); // strip markdown symbols for clearer TTS

        speak(speakOnly);
      }catch(err){
        out.innerHTML = "Server error. Try again.";
        console.error(err);
      }
    };

    rec.onerror = () => { out.innerHTML = "Didn’t catch that. Try again."; };
    rec.onend   = () => { if(out.innerHTML === "Listening…") out.innerHTML = ""; };
  });

  hint.textContent = "Tap Ask Now, speak, and hear the Can-Am answer.";
});
</script>
