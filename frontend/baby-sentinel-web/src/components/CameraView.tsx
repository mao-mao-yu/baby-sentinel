// 摄像头面板 — go2rtc WebRTC 接入。行为对齐旧 index.html startWebRTC()/stopWebRTC()：
//  - cam_ok=true   → 拨 WHEP（POST SDP 到 go2rtc /api/webrtc?src=baby）
//  - cam_ok=false  → tear down PeerConnection
//  - ICE failed    → 3s 后重连
//  - 12s 看门狗     → video.readyState 长时间 < HAVE_CURRENT_DATA 强制重拨
//  - visibilitychange→ 回前台时强制重连（iOS Safari 后台会静默杀 WebRTC）

import { useEffect, useRef, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";
import { useT } from "@/i18n";
import { useGo2rtcPort } from "@/api/manager-config";
import { cn } from "@/lib/utils";

export function CameraView() {
  const T = useT();
  const go2rtcPort = useGo2rtcPort();

  // 注意：CameraView 不再依赖 sensor.cam_ok。
  // 历史教训：cam_ok 由 backend go2rtc_monitor 通过 WS 广播，所有浏览器同步收到。
  // 一旦后端 monitor 误判（比如 go2rtc HTTP API 偶发 bug），所有客户端会同步拆掉
  // 健康的 WebRTC PC 重建 → 死循环 flicker。让 WebRTC 自己 SDP fetch 成功/失败决定
  // 是否 retry 才稳定。Header 上的"摄像头"pill 还是看 cam_ok 显示状态。

  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [live, setLive] = useState(false);
  // 默认开声音（实时监控场景需要听到孩子声音）。Windows Chrome / Edge 的 autoplay
  // 政策几乎肯定首次拒绝带声播放——下面 ontrack 的 play().catch 回退到 muted 并把
  // autoMutedRef.current 置 true。配合一个 document 全局 click/touch 监听：只要 ref
  // 为 true，下次用户随便在页面任何地方点一下就尝试 unmute（用户交互被浏览器算成
  // engagement，play() 会通过）。
  const [muted, setMuted] = useState(false);
  const autoMutedRef = useRef(false);   // true = 浏览器逼静音；用户主动 mute 时不置位
  // bumping retryToken 会让连接 effect 重跑——ICE failed / watchdog / 回前台 都用它触发重连
  const [retryToken, setRetryToken] = useState(0);

  // ── 主连接 effect ──────────────────────────────────────────────────
  // mount 时建立 WebRTC，go2rtcPort / retryToken 变化时重建。SDP fetch 失败会
  // 走 catch 5s 后 retry，无需 cam_ok 提前阻断。
  useEffect(() => {
    let cancelled = false;
    let pc: RTCPeerConnection | null = null;

    const start = async () => {
      pc = new RTCPeerConnection({ iceServers: [] });
      pcRef.current = pc;
      const remoteStream = new MediaStream();

      pc.addTransceiver("video", { direction: "recvonly" });
      pc.addTransceiver("audio", { direction: "recvonly" });

      pc.ontrack = (ev) => {
        remoteStream.addTrack(ev.track);
        if (ev.track.kind === "video" && videoRef.current) {
          const v = videoRef.current;
          v.srcObject = remoteStream;
          // iOS Safari 在 srcObject 改了之后必须 load() 一下，否则 play() 静默失败
          v.load();
          // 默认带声音播；autoplay 政策可能 reject → 回退 muted 并标记
          // autoMutedRef，下面 document 监听用户首次交互时自动尝试恢复声音。
          v.play().catch(() => {
            v.muted = true;
            setMuted(true);
            autoMutedRef.current = true;
            v.play().catch(() => {
              setTimeout(() => v.play().catch(() => {}), 400);
            });
          });
          setLive(true);
        }
      };

      // ICE 重连守卫：建连阶段 ICE 偶尔会 new → checking → failed → checking →
      // connected 闪过 failed 一下；如果无脑响应这次 failed，3s 后会把刚连上的
      // PC 拆了重来，造成"连接 ↔ 正常"横跳。只在曾经 connected 过之后才认这次
      // failed/disconnected 为真死亡，触发重连。
      let wasConnected = false;
      pc.oniceconnectionstatechange = () => {
        if (!pc) return;
        if (pc.iceConnectionState === "connected" ||
            pc.iceConnectionState === "completed") {
          wasConnected = true;
        }
        if (pc.iceConnectionState === "failed" && wasConnected && !cancelled) {
          setTimeout(() => setRetryToken((n) => n + 1), 3000);
        }
      };

      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        // 等 ICE gathering 完成（最多 3s）
        await new Promise<void>((resolve) => {
          if (!pc || pc.iceGatheringState === "complete") return resolve();
          const onChange = () => {
            if (pc?.iceGatheringState === "complete") resolve();
          };
          pc.addEventListener("icegatheringstatechange", onChange);
          setTimeout(resolve, 3000);
        });
        if (cancelled || pcRef.current !== pc) return;

        const url = `http://${location.hostname}:${go2rtcPort}/api/webrtc?src=baby`;
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
          body: pc.localDescription!.sdp,
        });
        if (!resp.ok) throw new Error(`go2rtc ${resp.status}`);
        const answerSdp = await resp.text();
        if (cancelled || pcRef.current !== pc) return;
        await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
      } catch (e) {
        console.warn("WebRTC connect failed:", e);
        if (!cancelled) setTimeout(() => setRetryToken((n) => n + 1), 5000);
      }
    };

    start();

    return () => {
      cancelled = true;
      pc?.close();
      if (pcRef.current === pc) pcRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
      setLive(false);
    };
  }, [go2rtcPort, retryToken]);

  // 注：之前这里有"帧停滞看门狗"（先 readyState、再 currentTime、再 framesDecoded
  // 三个版本），都会跟 ICE 建连阶段抢着触发 retryToken，造成"连接 ↔ 正常"横跳。
  // 现在主动重连只由两条路径触发：
  //   1) ICE failed（且必须曾经 connected 过，见上面 wasConnected 守卫）
  //   2) visibilitychange（页面回前台时刷一次，覆盖 iOS 后台 throttle 后的 dead PC）
  // 如果未来重新引入 watchdog，要确保它在握手期间静默（pc.connectionState !==
  // "connected" 时不计 stall），并且要用 ref 跨 retry 重置基线。

  // ── 回前台强制重连 ────────────────────────────────────────────────
  useEffect(() => {
    const onVis = () => {
      if (!document.hidden) {
        // 用 timeout 让浏览器先把 throttle 状态恢复回来
        setTimeout(() => setRetryToken((n) => n + 1), 500);
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  // ── 静音同步 ────────────────────────────────────────────────────
  useEffect(() => {
    if (videoRef.current) videoRef.current.muted = muted;
  }, [muted]);

  // ── 浏览器 autoplay 拒绝声音后，用户首次交互即自动尝试恢复 ──────
  // 监听整个 document 的 click / touchend——用户做任何操作都算 engagement，
  // play(unmuted) 这时通常会通过。autoMutedRef 为 false 时短路，不打扰用户主动选静音。
  useEffect(() => {
    const tryUnmute = () => {
      if (!autoMutedRef.current) return;
      const v = videoRef.current;
      if (!v) return;
      v.muted = false;
      v.play()
        .then(() => {
          setMuted(false);
          autoMutedRef.current = false;
        })
        .catch(() => {
          // 还是被拒（极少见）→ 保留静音，下次交互再试
          v.muted = true;
        });
    };
    document.addEventListener("click", tryUnmute);
    document.addEventListener("touchend", tryUnmute);
    return () => {
      document.removeEventListener("click", tryUnmute);
      document.removeEventListener("touchend", tryUnmute);
    };
  }, []);

  // mobile (<md): aspect-video 保 16:9，跟外层 main 一起滚
  // md+: aspect-auto + h-full，吃掉左列 flex-1 的剩余高度；视频内部 object-contain 自适应黑边
  return (
    <div className="relative mx-auto aspect-video w-full overflow-hidden rounded-md bg-black md:aspect-auto md:h-full">
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className={cn(
          "absolute inset-0 h-full w-full object-contain",
          live ? "opacity-100" : "opacity-0",
        )}
      />

      {/* Placeholder：未 live 时显示 */}
      {!live && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 text-center text-muted-foreground">
          <div className="text-4xl">📹</div>
          <p className="text-sm">{T.camWaiting}</p>
          <p className="text-xs opacity-70">{T.camHint}</p>
        </div>
      )}

      {/* 左上角红点 LIVE / 灰底"离线" */}
      <div className={cn(
        "absolute left-2 top-2 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px]",
        live
          ? "bg-black/50 text-white"
          : "bg-black/40 text-muted-foreground",
      )}>
        <span className={cn("size-1.5 rounded-full",
                            live ? "animate-pulse bg-destructive shadow-[0_0_6px_rgba(239,68,68,0.9)]" : "bg-muted-foreground")} />
        {live ? T.live : T.offline}
      </div>

      {/* 静音切换：只在 live 时显示 */}
      {live && (
        <button
          type="button"
          onClick={() => {
            // 用户接管音量控制 → 取消"自动恢复"标记
            autoMutedRef.current = false;
            setMuted((m) => !m);
          }}
          title={muted ? T.muteOn : T.muteOff}
          className="absolute right-2 top-2 inline-flex size-8 items-center justify-center rounded-full bg-black/60 text-white transition hover:bg-black/80"
        >
          {muted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
        </button>
      )}
    </div>
  );
}
