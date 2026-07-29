import type { CSSProperties, ReactNode } from "react";

// AI 가 생성한 문장에서 강조할 부분을 `**...**` 로 표시한다. LLM 출력에 raw HTML 을 허용하면
// 마크업이 깨지거나 주입 위험이 생기므로, 굵기 하나만 지원하고 나머지는 React 가 그대로
// 이스케이프하도록 문자열을 쪼개 <strong> 으로만 감싼다.
const EMPHASIS_PATTERN = /(\*\*[^*]+\*\*)/g;

/**
 * 굵기를 표현할 수 없는 자리(메일 프리헤더 등)를 위해 마커만 걷어낸다. 그냥 두면 받은 편지함
 * 미리보기에 `**...**` 가 그대로 노출된다.
 */
export function stripEmphasis(text: string) {
  return text.replace(EMPHASIS_PATTERN, (part) => part.slice(2, -2));
}

export function renderEmphasis(text: string, strongStyle?: CSSProperties): ReactNode[] {
  return text.split(EMPHASIS_PATTERN).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={index} style={strongStyle}>
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}
