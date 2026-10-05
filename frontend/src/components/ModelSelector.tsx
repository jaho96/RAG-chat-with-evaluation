import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Zap } from "lucide-react";
import { MODEL_OPTIONS, ModelOption } from "../types";

interface Props {
  selected: ModelOption;
  onChange: (option: ModelOption) => void;
}

// 그룹별로 모델 묶기
const groupedModels = MODEL_OPTIONS.reduce<Record<string, ModelOption[]>>((acc, m) => {
  if (!acc[m.group]) acc[m.group] = [];
  acc[m.group].push(m);
  return acc;
}, {});

const FREE_GROUPS = ["Groq", "Google Gemini"];
const PAID_GROUPS = ["OpenAI", "Claude"];

export default function ModelSelector({ selected, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});
  const ref = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      const insideBtn = ref.current?.contains(target);
      const insideDropdown = dropdownRef.current?.contains(target);
      if (!insideBtn && !insideDropdown) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleOpen = () => {
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom - 8;
      setDropdownStyle({
        position: "fixed",
        top: rect.bottom + 4,
        left: rect.left,
        width: rect.width,
        maxHeight: Math.min(384, spaceBelow),
        zIndex: 9999,
      });
    }
    setOpen((o) => !o);
  };

  return (
    <div ref={ref}>
      {/* 선택된 모델 버튼 */}
      <button
        ref={btnRef}
        onClick={handleOpen}
        className="w-full flex items-center justify-between gap-2 border border-gray-300 rounded-lg px-3 py-2 bg-white text-sm hover:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          {selected.free && (
            <span className="shrink-0 inline-flex items-center gap-0.5 text-xs bg-emerald-100 text-emerald-700 rounded-full px-1.5 py-0.5 font-medium">
              <Zap size={10} />
              무료
            </span>
          )}
          <span className="truncate text-gray-800">{selected.label}</span>
          <span className="shrink-0 text-xs text-gray-400">{selected.group}</span>
        </div>
        <ChevronDown size={14} className={`shrink-0 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* 드롭다운 패널 — portal로 body에 렌더링 */}
      {open && createPortal(
        <div ref={dropdownRef} style={dropdownStyle} className="bg-white border border-gray-200 rounded-xl shadow-lg overflow-y-auto">
          {/* 무료 섹션 */}
          <div className="px-3 pt-2 pb-1">
            <p className="text-xs font-semibold text-emerald-600 uppercase tracking-wider flex items-center gap-1">
              <Zap size={10} /> 무료
            </p>
          </div>
          {FREE_GROUPS.map((group) =>
            groupedModels[group] ? (
              <div key={group}>
                <p className="px-3 pt-1 text-xs text-gray-400 font-medium">{group}</p>
                {groupedModels[group].map((m) => (
                  <ModelItem key={`${m.provider}::${m.model}`} m={m} selected={selected} onChange={(opt) => { onChange(opt); setOpen(false); }} />
                ))}
              </div>
            ) : null
          )}

          {/* 유료 섹션 — MODEL_OPTIONS에 유료 모델이 있을 때만 표시 */}
          {PAID_GROUPS.some((g) => groupedModels[g]) && (
            <>
              <div className="mx-3 my-1.5 border-t border-gray-100" />
              <div className="px-3 pt-1 pb-1">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">유료</p>
              </div>
              {PAID_GROUPS.map((group) =>
                groupedModels[group] ? (
                  <div key={group}>
                    <p className="px-3 pt-1 text-xs text-gray-400 font-medium">{group}</p>
                    {groupedModels[group].map((m) => (
                      <ModelItem key={`${m.provider}::${m.model}`} m={m} selected={selected} onChange={(opt) => { onChange(opt); setOpen(false); }} />
                    ))}
                  </div>
                ) : null
              )}
            </>
          )}
          <div className="h-2" />
        </div>,
        document.body
      )}
    </div>
  );
}

function ModelItem({
  m,
  selected,
  onChange,
}: {
  m: ModelOption;
  selected: ModelOption;
  onChange: (m: ModelOption) => void;
}) {
  const isSelected = m.provider === selected.provider && m.model === selected.model;
  return (
    <button
      onClick={() => onChange(m)}
      className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors ${
        isSelected ? "bg-blue-50 text-blue-700" : "text-gray-700 hover:bg-gray-50"
      }`}
    >
      {m.free && (
        <span className="shrink-0 inline-flex items-center gap-0.5 text-xs bg-emerald-100 text-emerald-700 rounded-full px-1.5 py-0.5 font-medium">
          <Zap size={9} />
          무료
        </span>
      )}
      <span>{m.label}</span>
      {isSelected && <span className="ml-auto text-blue-500 text-xs">선택됨</span>}
    </button>
  );
}
