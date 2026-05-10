import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Settings } from "lucide-react";
import { api } from "@/api/manager";
import { Button } from "@/components/ui/button";
import { ServiceCard } from "@/components/ServiceCard";
import { ConfigDialog } from "@/components/ConfigDialog";
import { LangProvider, asLang, useT } from "@/i18n";

export default function App() {
  // /api/manager/config 一次拉取 + cache：language 是 single source of truth，
  // ConfigDialog 保存后 invalidate 会触发本 query 重拉，下游所有 useT()
  // 自动重渲染。React Query 自动 dedupe，ConfigDialog 自己再用同 key 不会多发请求。
  const cfgQ = useQuery({ queryKey: ["config"], queryFn: api.getConfig });
  const lang = asLang((cfgQ.data?.config as { language?: unknown } | undefined)?.language);

  return (
    <LangProvider lang={lang}>
      <AppInner />
    </LangProvider>
  );
}

function AppInner() {
  const T = useT();
  const { data, isLoading, error } = useQuery({
    queryKey: ["status"],
    queryFn:  api.status,
    refetchInterval: 2000,
  });

  // 主界面 / 回放页运行在不同的 web 服务（端口取自 config.web_port，默认 8080），
  // 不是 manager 自己。所以这里要拼绝对 URL 跨端口跳转。
  const cfgQ = useQuery({ queryKey: ["config"], queryFn: api.getConfig });
  const webPort = (cfgQ.data?.config as { web_port?: number } | undefined)?.web_port ?? 8080;
  const mainUrl     = `http://${location.hostname}:${webPort}/`;
  const playbackUrl = `http://${location.hostname}:${webPort}/playback`;

  const [globalOpen, setGlobalOpen] = useState(false);

  // iOS Safari 上 sticky / fixed 都跟 layout viewport 走，URL bar 折叠期间会"飘"
  // 一段才贴住——这是 Safari 的设计，无法用 CSS 层面的 sticky/fixed 修。
  // 只能让 page 自己不滚动（outer overflow-hidden），把滚动收到 <main> 内部：
  // body 不滚 → URL bar 永不折叠 → header 在 flex column 顶部天然不动。
  // 代价：URL bar 永远显示，吃 ~70px 屏幕空间。
  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-background text-foreground">
      <header className="shrink-0 border-b border-border/60 bg-background px-6 py-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <h1 className="text-xl font-semibold">{T.mgrTitle}</h1>
          <a href={mainUrl}     className="text-sm text-muted-foreground hover:text-foreground">{T.mgrLinkMain}</a>
          <a href={playbackUrl} className="text-sm text-muted-foreground hover:text-foreground">{T.mgrLinkPlayback}</a>
          <Button variant="ghost" size="icon" className="ml-auto"
                  title={T.mgrSettings}
                  onClick={() => setGlobalOpen(true)}>
            <Settings className="size-4" />
          </Button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-3 py-4">
        {isLoading && <p className="text-muted-foreground">loading…</p>}
        {error    && <p className="text-destructive">{String(error)}</p>}
        {data && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {Object.entries(data).map(([svc, state]) => (
              <ServiceCard key={svc} svc={svc} state={state} />
            ))}
          </div>
        )}
      </main>

      <ConfigDialog svc="global"
                    open={globalOpen} onOpenChange={setGlobalOpen}
                    onSavedRestart={null}
                    titleOverride={T.cfgGlobalTitle} />
    </div>
  );
}
