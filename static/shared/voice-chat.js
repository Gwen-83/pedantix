(function () {
  "use strict";

  const ICE_SERVERS = [
    {
      urls: ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"],
    },
    {
      urls: ["turn:openrelay.metered.ca:80", "turn:openrelay.metered.ca:443"],
      username: "openrelayproject",
      credential: "openrelayproject",
    },
  ];
  const ICE_GATHERING_TIMEOUT_MS = 2500;
  const READY_RETRY_MS = 8000;
  const JOIN_CONFIRM_TIMEOUT_MS = 10000;
  const SYNC_INTERVAL_MS = 4000;

  function randomId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  }

  function microphoneError(error) {
    const name = error?.name || "";
    if (name === "NotAllowedError" || name === "SecurityError") {
      return new Error(
        "Accès au micro refusé. Autorisez le micro dans le navigateur pour utiliser le chat vocal.",
      );
    }
    if (name === "NotFoundError" || name === "OverconstrainedError") {
      return new Error("Aucun micro n’a été détecté sur cet appareil.");
    }
    if (name === "NotReadableError" || name === "AbortError") {
      return new Error(
        "Le micro est déjà utilisé par une autre application ou est indisponible.",
      );
    }
    return new Error("Impossible d’accéder au micro.");
  }

  function waitForIceGathering(pc) {
    if (pc.iceGatheringState === "complete") return Promise.resolve();
    return new Promise((resolve) => {
      const finish = () => {
        clearTimeout(timer);
        pc.removeEventListener("icegatheringstatechange", onStateChange);
        pc.removeEventListener("icecandidate", onCandidate);
        resolve();
      };
      const onStateChange = () => {
        if (pc.iceGatheringState === "complete") finish();
      };
      const onCandidate = (event) => {
        if (!event.candidate) finish();
      };
      const timer = setTimeout(finish, ICE_GATHERING_TIMEOUT_MS);
      pc.addEventListener("icegatheringstatechange", onStateChange);
      pc.addEventListener("icecandidate", onCandidate);
    });
  }

  function createVoiceChat({ playerId, sendSignal, requestLeave }) {
    let voiceState = { enabled: false, members: [], muted: {} };
    let localStream = null;
    let acquiring = false;
    let membershipConfirmed = false;
    let joinDeadline = 0;
    let leaveRequested = false;
    let syncTimer = null;
    let audioUnlockHandler = null;
    const peers = new Map();
    const pendingReady = new Map();
    const queues = new Map();

    const isMember = () =>
      voiceState.enabled && voiceState.members.includes(playerId);
    const isActive = () => Boolean(localStream) && isMember();
    const isInitiator = (peerId) => playerId < peerId;

    function applyMute() {
      if (!localStream) return;
      const muted = Boolean(voiceState.muted[playerId]);
      localStream.getAudioTracks().forEach((track) => {
        track.enabled = !muted;
      });
    }

    function closePeer(peerId) {
      const peer = peers.get(peerId);
      if (!peer) return;
      peers.delete(peerId);
      peer.pc.ontrack = null;
      peer.pc.onconnectionstatechange = null;
      peer.pc.oniceconnectionstatechange = null;
      try {
        peer.pc.close();
      } catch (error) {
        console.warn("Fermeture de connexion vocale impossible :", error);
      }
      if (peer.audio) {
        peer.audio.srcObject = null;
        peer.audio.remove();
      }
    }

    function closeAllPeers() {
      [...peers.keys()].forEach(closePeer);
      pendingReady.clear();
    }

    function releaseAudioUnlock() {
      if (!audioUnlockHandler) return;
      document.removeEventListener("pointerdown", audioUnlockHandler, true);
      document.removeEventListener("keydown", audioUnlockHandler, true);
      audioUnlockHandler = null;
    }

    function armAudioUnlock() {
      if (audioUnlockHandler) return;
      audioUnlockHandler = () => {
        releaseAudioUnlock();
        peers.forEach((peer) => {
          if (peer.audio) playAudio(peer.audio);
        });
      };
      document.addEventListener("pointerdown", audioUnlockHandler, true);
      document.addEventListener("keydown", audioUnlockHandler, true);
    }

    function playAudio(audio) {
      const playing = audio.play();
      if (playing?.catch) playing.catch(armAudioUnlock);
    }

    function createPeer(peerId, session) {
      closePeer(peerId);
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      const peer = { pc, session, audio: null };
      peers.set(peerId, peer);
      localStream
        .getAudioTracks()
        .forEach((track) => pc.addTrack(track, localStream));
      pc.ontrack = (event) => {
        if (peers.get(peerId) !== peer) return;
        if (!peer.audio) {
          peer.audio = document.createElement("audio");
          peer.audio.autoplay = true;
          peer.audio.setAttribute("playsinline", "");
          peer.audio.hidden = true;
          document.body.append(peer.audio);
        }
        peer.audio.srcObject = event.streams[0] || new MediaStream([event.track]);
        playAudio(peer.audio);
      };
      const onStateChange = () => {
        if (peers.get(peerId) !== peer) return;
        if (pc.connectionState === "failed" || pc.iceConnectionState === "failed") {
          closePeer(peerId);
          sync();
        }
      };
      pc.onconnectionstatechange = onStateChange;
      pc.oniceconnectionstatechange = onStateChange;
      return peer;
    }

    async function startOffer(peerId) {
      const session = randomId();
      const peer = createPeer(peerId, session);
      await peer.pc.setLocalDescription(await peer.pc.createOffer());
      await waitForIceGathering(peer.pc);
      if (peers.get(peerId) !== peer) return;
      sendSignal(peerId, {
        kind: "offer",
        session,
        sdp: peer.pc.localDescription.sdp,
      });
    }

    async function acceptOffer(peerId, signal) {
      pendingReady.delete(peerId);
      const peer = createPeer(peerId, signal.session);
      await peer.pc.setRemoteDescription({ type: "offer", sdp: signal.sdp });
      await peer.pc.setLocalDescription(await peer.pc.createAnswer());
      await waitForIceGathering(peer.pc);
      if (peers.get(peerId) !== peer) return;
      sendSignal(peerId, {
        kind: "answer",
        session: signal.session,
        sdp: peer.pc.localDescription.sdp,
      });
    }

    async function acceptAnswer(peerId, signal) {
      const peer = peers.get(peerId);
      if (
        !peer ||
        peer.session !== signal.session ||
        peer.pc.signalingState !== "have-local-offer"
      )
        return;
      await peer.pc.setRemoteDescription({ type: "answer", sdp: signal.sdp });
    }

    function enqueue(peerId, task) {
      const previous = queues.get(peerId) || Promise.resolve();
      const next = previous.then(task).catch((error) => {
        console.warn("Connexion vocale interrompue :", error);
        closePeer(peerId);
      });
      queues.set(peerId, next);
      next.then(() => {
        if (queues.get(peerId) === next) queues.delete(peerId);
      });
    }

    function sync() {
      if (localStream && !membershipConfirmed && Date.now() > joinDeadline) {
        stopLocalStream();
        return;
      }
      if (!isActive()) {
        closeAllPeers();
        return;
      }
      applyMute();
      const others = voiceState.members.filter(
        (memberId) => memberId && memberId !== playerId,
      );
      [...peers.keys()]
        .filter((peerId) => !others.includes(peerId))
        .forEach(closePeer);
      [...pendingReady.keys()]
        .filter((peerId) => !others.includes(peerId))
        .forEach((peerId) => pendingReady.delete(peerId));
      const now = Date.now();
      others.forEach((peerId) => {
        if (peers.has(peerId) || isInitiator(peerId)) return;
        const lastReady = pendingReady.get(peerId);
        if (lastReady && now - lastReady < READY_RETRY_MS) return;
        pendingReady.set(peerId, now);
        sendSignal(peerId, { kind: "ready", session: randomId() });
      });
    }

    function stopLocalStream() {
      closeAllPeers();
      releaseAudioUnlock();
      if (syncTimer) clearInterval(syncTimer);
      syncTimer = null;
      membershipConfirmed = false;
      if (!localStream) return;
      localStream.getTracks().forEach((track) => track.stop());
      localStream = null;
    }

    function update(nextState) {
      voiceState = {
        enabled: Boolean(nextState?.enabled),
        members: Array.isArray(nextState?.members) ? nextState.members : [],
        muted:
          nextState?.muted && typeof nextState.muted === "object"
            ? nextState.muted
            : {},
      };
      const member = isMember();
      if (!member) leaveRequested = false;
      if (localStream) {
        if (!voiceState.enabled || (membershipConfirmed && !member)) {
          stopLocalStream();
          return;
        }
        if (member) membershipConfirmed = true;
      } else if (member && !acquiring && !leaveRequested) {
        leaveRequested = true;
        requestLeave?.();
      }
      sync();
    }

    async function join() {
      if (localStream) return true;
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(
          "Le navigateur ne permet pas d’accéder au micro ici (une connexion HTTPS est nécessaire).",
        );
      }
      if (!window.RTCPeerConnection) {
        throw new Error("Le chat vocal n’est pas disponible dans ce navigateur.");
      }
      acquiring = true;
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
      } catch (error) {
        throw microphoneError(error);
      } finally {
        acquiring = false;
      }
      if (!voiceState.enabled) {
        stream.getTracks().forEach((track) => track.stop());
        return false;
      }
      localStream = stream;
      membershipConfirmed = isMember();
      joinDeadline = Date.now() + JOIN_CONFIRM_TIMEOUT_MS;
      leaveRequested = false;
      applyMute();
      syncTimer = setInterval(sync, SYNC_INTERVAL_MS);
      sync();
      return true;
    }

    function setMuted(muted) {
      voiceState.muted = { ...voiceState.muted, [playerId]: Boolean(muted) };
      applyMute();
    }

    function handleSignal(message) {
      const from = message?.from_player_id;
      const signal = message?.signal;
      if (!from || from === playerId || !signal || !isActive()) return;
      enqueue(from, async () => {
        if (!isActive()) return;
        if (signal.kind === "ready") {
          if (isInitiator(from)) await startOffer(from);
        } else if (signal.kind === "offer" && signal.sdp) {
          await acceptOffer(from, signal);
        } else if (signal.kind === "answer" && signal.sdp) {
          await acceptAnswer(from, signal);
        }
      });
    }

    window.addEventListener("pagehide", stopLocalStream);

    return {
      update,
      join,
      leave: stopLocalStream,
      setMuted,
      handleSignal,
      isJoined: () => Boolean(localStream),
    };
  }

  window.createVoiceChat = createVoiceChat;
})();
