interface TopbarProps {
  onMenuClick: () => void;
}

export default function Topbar({
  onMenuClick,
}: TopbarProps) {
  return (
    <header className="flex h-20 items-center justify-between border-b border-zinc-800 bg-zinc-950/80 px-4 backdrop-blur sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Open navigation"
          className="rounded-lg border border-zinc-800 px-3 py-2 text-zinc-400 hover:bg-zinc-900 hover:text-white lg:hidden"
          onClick={onMenuClick}
        >
          ☰
        </button>

        <div>
          <p className="text-sm font-medium text-zinc-400">
            Platform Console
          </p>
          <h1 className="text-lg font-semibold text-white">
            CloudForge AI
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900 px-3 py-2 sm:flex">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          <span className="text-xs text-zinc-400">
            Local environment
          </span>
        </div>

        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white">
          NS
        </div>
      </div>
    </header>
  );
}
