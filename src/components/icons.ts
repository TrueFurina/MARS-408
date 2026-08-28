/** MARS-408 SVG 图标系统 — 替代全部 emoji */

export const icons = {
  // 品牌 — 紫蓝渐变多智能体节点徽标（中心编排节点 + 408 四科节点）
  logo: `<svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="MARS-408 408">
    <defs>
      <linearGradient id="nlGrad" x1="6" y1="6" x2="34" y2="34" gradientUnits="userSpaceOnUse">
        <stop stop-color="#7c6af2"/>
        <stop offset="1" stop-color="#5b8bd8"/>
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="11" fill="url(#nlGrad)"/>
    <rect x="1" y="1" width="38" height="38" rx="10" fill="none" stroke="rgba(255,255,255,0.18)" stroke-width="1"/>
    <g stroke="#ffffff" stroke-width="2" stroke-linecap="round" opacity="0.9">
      <line x1="20" y1="20" x2="20" y2="9.5"/>
      <line x1="20" y1="20" x2="30.5" y2="20"/>
      <line x1="20" y1="20" x2="20" y2="30.5"/>
      <line x1="20" y1="20" x2="9.5" y2="20"/>
    </g>
    <g fill="#ffffff">
      <circle cx="20" cy="9.5" r="3.2"/>
      <circle cx="30.5" cy="20" r="3.2"/>
      <circle cx="20" cy="30.5" r="3.2"/>
      <circle cx="9.5" cy="20" r="3.2"/>
    </g>
    <circle cx="20" cy="20" r="5.4" fill="#ffffff"/>
    <circle cx="20" cy="20" r="2.6" fill="url(#nlGrad)"/>
  </svg>`,

  // 导航
  menu: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
    <line x1="4" y1="6" x2="20" y2="6"/>
    <line x1="4" y1="12" x2="20" y2="12"/>
    <line x1="4" y1="18" x2="20" y2="18"/>
  </svg>`,

  close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
    <line x1="6" y1="6" x2="18" y2="18"/>
    <line x1="18" y1="6" x2="6" y2="18"/>
  </svg>`,

  user: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="8" r="4"/>
    <path d="M20 21C20 16.5817 16.4183 13 12 13C7.58172 13 4 16.5817 4 21"/>
  </svg>`,

  // 聊天
  send: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>`,

  attach: `<svg viewBox="0 0 16 18" fill="currentColor" stroke="none" stroke-linecap="round" stroke-linejoin="round">
    <path d="M5.55 9.75V5H6.95V9.75C6.95 10.33 7.42 10.8 8 10.8C8.58 10.8 9.05 10.33 9.05 9.75V4.5C9.05 2.95 7.8 1.7 6.25 1.7C4.7 1.7 3.45 2.95 3.45 4.5V9.75C3.45 12.26 5.49 14.3 8 14.3C10.51 14.3 12.55 12.26 12.55 9.75V4H13.95V9.75C13.95 13.04 11.29 15.7 8 15.7C4.71 15.7 2.05 13.04 2.05 9.75V4.5C2.05 2.18 3.93 0.3 6.25 0.3C8.57 0.3 10.45 2.18 10.45 4.5V9.75C10.45 11.1 9.35 12.2 8 12.2C6.65 12.2 5.55 11.1 5.55 9.75Z"/>
  </svg>`,

  mic: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 1C10.3431 1 9 2.34315 9 4V12C9 13.6569 10.3431 15 12 15C13.6569 15 15 13.6569 15 12V4C15 2.34315 13.6569 1 12 1Z"/>
    <path d="M19 10V12C19 15.866 15.866 19 12 19C8.13401 19 5 15.866 5 12V10"/>
    <line x1="12" y1="19" x2="12" y2="23"/>
    <line x1="8" y1="23" x2="16" y2="23"/>
  </svg>`,

  chat: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 15C21 15.5304 20.7893 16.0391 20.4142 16.4142C20.0391 16.7893 19.5304 17 19 17H7L3 21V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H19C19.5304 3 20.0391 3.21071 20.4142 3.58579C20.7893 3.96086 21 4.46957 21 5V15Z"/>
  </svg>`,

  // AI / 助理
  sparkle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 3L14.5 9.5L21 12L14.5 14.5L12 21L9.5 14.5L3 12L9.5 9.5Z"/>
  </svg>`,

  robot: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="4" y="5" width="16" height="12" rx="4"/>
    <circle cx="9" cy="10" r="1.5" fill="currentColor"/>
    <circle cx="15" cy="10" r="1.5" fill="currentColor"/>
    <path d="M9 14C9.5 14.5 10.5 15 12 15C13.5 15 14.5 14.5 15 14"/>
    <line x1="12" y1="17" x2="12" y2="21"/>
    <line x1="8" y1="21" x2="16" y2="21"/>
  </svg>`,

  book: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M4 19.5C4 18.837 4.26339 18.2011 4.73223 17.7322C5.20107 17.2634 5.83696 17 6.5 17H20"/>
    <path d="M6.5 2H20V22H6.5C5.83696 22 5.20107 21.7366 4.73223 21.2678C4.26339 20.7989 4 20.163 4 19.5V4.5C4 3.83696 4.26339 3.20107 4.73223 2.73223C5.20107 2.26339 5.83696 2 6.5 2Z"/>
  </svg>`,

  document: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z"/>
    <path d="M14 2V8H20"/>
    <line x1="8" y1="13" x2="16" y2="13"/>
    <line x1="8" y1="17" x2="13" y2="17"/>
  </svg>`,

  // 学习 / 仪表盘
  dashboard: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="3" width="7" height="7" rx="1"/>
    <rect x="14" y="3" width="7" height="4" rx="1"/>
    <rect x="14" y="10" width="7" height="11" rx="1"/>
    <rect x="3" y="14" width="7" height="7" rx="1"/>
  </svg>`,

  quiz: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <line x1="12" y1="8" x2="12" y2="12"/>
    <line x1="12" y1="16" x2="12.01" y2="16"/>
  </svg>`,

  knowledge: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <circle cx="12" cy="12" r="8"/>
    <circle cx="12" cy="12" r="11"/>
  </svg>`,

  path: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="5" r="3"/>
    <circle cx="19" cy="12" r="3"/>
    <circle cx="5" cy="19" r="3"/>
    <path d="M12 8L16 10"/>
    <path d="M14 14L8 17"/>
  </svg>`,

  chart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 3V21H21"/>
    <rect x="7" y="10" width="4" height="8" rx="1"/>
    <rect x="15" y="6" width="4" height="12" rx="1"/>
  </svg>`,

  terminal: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2" y="3" width="20" height="18" rx="3"/>
    <path d="M6 8L10 12L6 16"/>
    <line x1="12" y1="16" x2="18" y2="16"/>
  </svg>`,

  agent: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="5"/>
    <circle cx="9" cy="10" r="1.5" fill="currentColor"/>
    <circle cx="15" cy="10" r="1.5" fill="currentColor"/>
    <path d="M9 15C9.5 15.75 10.5 16 12 16C13.5 16 14.5 15.75 15 15"/>
  </svg>`,

  setting: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15C19.2669 15.3016 19.2272 15.6362 19.286 15.9606C19.3448 16.285 19.4995 16.5843 19.73 16.82L19.79 16.88C19.976 17.0657 20.1235 17.2863 20.2241 17.5291C20.3248 17.7719 20.3766 18.0322 20.3766 18.295C20.3766 18.5578 20.3248 18.8181 20.2241 19.0609C20.1235 19.3037 19.976 19.5243 19.79 19.71C19.6043 19.896 19.3837 20.0435 19.1409 20.1441C18.8981 20.2448 18.6378 20.2966 18.375 20.2966C18.1122 20.2966 17.8519 20.2448 17.6091 20.1441C17.3663 20.0435 17.1457 19.896 16.96 19.71L16.9 19.65C16.6643 19.4195 16.365 19.2648 16.0406 19.206C15.7162 19.1472 15.3816 19.1869 15.08 19.32C14.7842 19.4468 14.532 19.6572 14.3543 19.9255C14.1766 20.1938 14.0813 20.5082 14.08 20.83V21C14.08 21.5304 13.8693 22.0391 13.4942 22.4142C13.1191 22.7893 12.6104 23 12.08 23C11.5496 23 11.0409 22.7893 10.6658 22.4142C10.2907 22.0391 10.08 21.5304 10.08 21V20.91C10.0723 20.579 9.96512 20.258 9.77251 19.9887C9.5799 19.7194 9.31074 19.5143 9 19.4C8.69838 19.2669 8.36381 19.2272 8.03941 19.286C7.71502 19.3448 7.41568 19.4995 7.18 19.73L7.12 19.79C6.93425 19.976 6.71368 20.1235 6.47088 20.2241C6.22808 20.3248 5.96783 20.3766 5.705 20.3766C5.44217 20.3766 5.18192 20.3248 4.93912 20.2241C4.69632 20.1235 4.47575 19.976 4.29 19.79C4.10405 19.6043 3.95653 19.3837 3.85588 19.1409C3.75523 18.8981 3.70343 18.6378 3.70343 18.375C3.70343 18.1122 3.75523 17.8519 3.85588 17.6091C3.95653 17.3663 4.10405 17.1457 4.29 16.96L4.35 16.9C4.58054 16.6643 4.73519 16.365 4.794 16.0406C4.85282 15.7162 4.81312 15.3816 4.68 15.08C4.55324 14.7842 4.34276 14.532 4.07447 14.3543C3.80618 14.1766 3.49179 14.0813 3.17 14.08H3C2.46957 14.08 1.96086 13.8693 1.58579 13.4942C1.21071 13.1191 1 12.6104 1 12.08C1 11.5496 1.21071 11.0409 1.58579 10.6658C1.96086 10.2907 2.46957 10.08 3 10.08H3.09C3.42099 10.0723 3.742 9.96512 4.0113 9.77251C4.28059 9.5799 4.48572 9.31074 4.6 9C4.73312 8.69838 4.77282 8.36381 4.714 8.03941C4.65519 7.71502 4.50054 7.41568 4.27 7.18L4.21 7.12C4.02405 6.93425 3.87653 6.71368 3.77588 6.47088C3.6706 6.22199 3.61613 5.95365 3.61613 5.6825C3.61613 5.41135 3.6706 5.14301 3.77588 4.89412C3.87653 4.65132 4.02405 4.43075 4.21 4.245C4.39575 4.05905 4.61632 3.91153 4.85912 3.81088C5.10192 3.71023 5.36217 3.65843 5.625 3.65843C5.88783 3.65843 6.14808 3.71023 6.39088 3.81088C6.63368 3.91153 6.85425 4.05905 7.04 4.245L7.1 4.31C7.33568 4.54054 7.63502 4.69519 7.95941 4.754C8.28381 4.81282 8.61838 4.77312 8.92 4.64C9.21576 4.51324 9.468 4.30276 9.64569 4.03447C9.82338 3.76618 9.91869 3.45179 9.92 3.13V3C9.92 2.46957 10.1307 1.96086 10.5058 1.58579C10.8809 1.21071 11.3896 1 11.92 1C12.4504 1 12.9591 1.21071 13.3342 1.58579C13.7093 1.96086 13.92 2.46957 13.92 3V3.09C13.9277 3.42099 14.0349 3.742 14.2275 4.0113C14.4201 4.28059 14.6893 4.48572 15 4.6C15.3016 4.73312 15.6362 4.77282 15.9606 4.714C16.285 4.65519 16.5843 4.50054 16.82 4.27L16.88 4.21C17.0657 4.02405 17.2863 3.87653 17.5291 3.77588C17.7719 3.6706 18.0322 3.61613 18.295 3.61613C18.5578 3.61613 18.8181 3.6706 19.0609 3.77588C19.3037 3.87653 19.5243 4.02405 19.71 4.21C19.896 4.39575 20.0435 4.61632 20.1441 4.85912C20.2448 5.10192 20.2966 5.36217 20.2966 5.625C20.2966 5.88783 20.2448 6.14808 20.1441 6.39088C20.0435 6.63368 19.896 6.85425 19.71 7.04L19.65 7.1C19.4195 7.33568 19.2648 7.63502 19.206 7.95941C19.1472 8.28381 19.1869 8.61838 19.32 8.92C19.4468 9.21576 19.6572 9.468 19.9255 9.64569C20.1938 9.82338 20.5082 9.91869 20.83 9.92H21C21.5304 9.92 22.0391 10.1307 22.4142 10.5058C22.7893 10.8809 23 11.3896 23 11.92C23 12.4504 22.7893 12.9591 22.4142 13.3342C22.0391 13.7093 21.5304 13.92 21 13.92H20.91C20.579 13.9277 20.258 14.0349 19.9887 14.2275C19.7194 14.4201 19.5143 14.6893 19.4 15Z"/>
  </svg>`,

  history: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <polyline points="12 6 12 12 16 14"/>
  </svg>`,

  bell: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M18 8C18 6.4087 17.3679 4.88258 16.2426 3.75736C15.1174 2.63214 13.5913 2 12 2C10.4087 2 8.88258 2.63214 7.75736 3.75736C6.63214 4.88258 6 6.4087 6 8C6 15 3 17 3 17H21C21 17 18 15 18 8Z"/>
    <path d="M13.73 21C13.5542 21.3031 13.3019 21.5547 12.9982 21.7295C12.6946 21.9044 12.3508 21.9965 12 21.9965C11.6492 21.9965 11.3054 21.9044 11.0018 21.7295C10.6981 21.5547 10.4458 21.3031 10.27 21"/>
  </svg>`,

  // 箭头
  chevronRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="9 18 15 12 9 6"/>
  </svg>`,

  // 杂项
  search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="11" cy="11" r="8"/>
    <line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>`,

  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>`,

  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <line x1="12" y1="5" x2="12" y2="19"/>
    <line x1="5" y1="12" x2="19" y2="12"/>
  </svg>`,

  // ── 特质 / 画像图标（替代 emoji）──
  brain: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 2C8 2 5 5 5 9C5 11 6 12.5 7 13.5C7.5 14 8 15 8 16C8 17.5 9 19 12 19C15 19 16 17.5 16 16C16 15 16.5 14 17 13.5C18 12.5 19 11 19 9C19 5 16 2 12 2Z"/>
    <path d="M12 19V22"/><line x1="9" y1="22" x2="15" y2="22"/>
  </svg>`,

  target: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
  </svg>`,

  chartUp: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 3V21H21"/><polyline points="7 14 12 9 17 5"/><line x1="17" y1="5" x2="17" y2="14"/>
  </svg>`,

  fire: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 22C17 22 21 18 21 13C21 8 17 5 14 2C12 4 10 5 10 8C10 8 8 6 6 7C6 10 7 12 7 14C7 17 9 20 12 22Z"/>
    <path d="M12 22C14 22 16 20 16 17C16 14 14 12 12 10C10 12 8 14 8 17C8 20 10 22 12 22Z"/>
  </svg>`,

  clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
  </svg>`,

  mountain: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M8 21L12 13L16 21"/><path d="M4 21L12 5L20 21"/><line x1="2" y1="21" x2="22" y2="21"/>
  </svg>`,

  muscle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M7 11V7C7 4.79 8.79 3 11 3H13C15.21 3 17 4.79 17 7V11"/>
    <path d="M5 11C5 9 7 7 9 7H15C17 7 19 9 19 11C19 13 17 15 15 15H9C7 15 5 13 5 11Z"/>
  </svg>`,

  eye: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M1 12C1 12 5 4 12 4C19 4 23 12 23 12C23 12 19 20 12 20C5 20 1 12 1 12Z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>`,

  ear: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 2C8 2 5 5.5 5 9.5C5 13 7 15 9 17C10 18 11 19 11 21"/>
    <path d="M12 2C16 2 19 5.5 19 9.5C19 13 17 15 15 17C14 18 13 19 13 21"/>
    <circle cx="12" cy="9.5" r="2.5"/>
  </svg>`,

  pen: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M17 3L21 7L7 21H3V17L17 3Z"/><line x1="15" y1="5" x2="19" y2="9"/>
  </svg>`,

  bookOpen: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M2 3H6C9 3 12 5 12 8V21C12 18 9 16 6 16H2V3Z"/>
    <path d="M22 3H18C15 3 12 5 12 8V21C12 18 15 16 18 16H22V3Z"/>
  </svg>`,

  lock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
    <path d="M7 11V7C7 4.24 9.24 2 12 2C14.76 2 17 4.24 17 7V11"/>
  </svg>`,

  mapPin: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 2C8.13 2 5 5.13 5 9C5 14.25 12 22 12 22C12 22 19 14.25 19 9C19 5.13 15.87 2 12 2Z"/>
    <circle cx="12" cy="9" r="2.5"/>
  </svg>`,

  checkCircle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M22 11.08V12C22 16.42 18.42 20 14 20H12C8 20 5 17 5 13V12"/>
    <polyline points="22 4 12 14.01 9 11.01"/>
  </svg>`,

  lightbulb: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M9 21H15"/><path d="M12 3C8.24 3 5 6.24 5 10C5 12.5 6.5 14.5 8.5 15.5C9 15.8 9.5 16.3 9.5 17V18C9.5 18.5 10 19 10.5 19H13.5C14 19 14.5 18.5 14.5 18V17C14.5 16.3 15 15.8 15.5 15.5C17.5 14.5 19 12.5 19 10C19 6.24 15.76 3 12 3Z"/>
  </svg>`,

  sparkleSmall: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M8 1L9.5 5.5L14 8L9.5 10.5L8 15L6.5 10.5L2 8L6.5 5.5Z"/>
  </svg>`,

  fileText: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M14 2H6C5.47 2 4.96 2.21 4.59 2.59C4.21 2.96 4 3.47 4 4V20C4 20.53 4.21 21.04 4.59 21.41C4.96 21.79 5.47 22 6 22H18C18.53 22 19.04 21.79 19.41 21.41C19.79 21.04 20 20.53 20 20V8L14 2Z"/>
    <polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/>
  </svg>`,

  clipboard: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M16 4H18C18.53 4 19.04 4.21 19.41 4.59C19.79 4.96 20 5.47 20 6V20C20 20.53 19.79 21.04 19.41 21.41C19.04 21.79 18.53 22 18 22H6C5.47 22 4.96 21.79 4.59 21.41C4.21 21.04 4 20.53 4 20V6C4 5.47 4.21 4.96 4.59 4.59C4.96 4.21 5.47 4 6 4H8"/>
    <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
  </svg>`,

  palette: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="13.5" cy="6.5" r="1.5" fill="currentColor"/><circle cx="17.5" cy="10.5" r="1.5" fill="currentColor"/><circle cx="8.5" cy="7.5" r="1.5" fill="currentColor"/><circle cx="6.5" cy="12.5" r="1.5" fill="currentColor"/>
    <path d="M12 2C6.5 2 2 6.5 2 12C2 17.5 6.5 22 12 22C12.9 22 13.5 21.3 13.5 20.4C13.5 19.5 13.1 18.8 13.1 17.9C13.1 16.5 14.2 15.5 15.6 15.5H17.6C21.1 15.5 22 13 22 10.5C22 5.8 17.5 2 12 2Z"/>
  </svg>`,

  search2: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>`,

  graduation: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M22 10L12 5L2 10L12 15L22 10Z"/>
    <path d="M6 12V17C6 17 9 20 12 20C15 20 18 17 18 17V12"/>
    <line x1="22" y1="10" x2="22" y2="16"/>
  </svg>`,

  package: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M16.5 9.5L22 12L12 17L2 12L7.5 9.5"/>
    <path d="M22 12V17L12 22L2 17V12"/>
    <path d="M22 7L12 12L2 7L12 2L22 7Z"/>
  </svg>`,

  rocket: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M4.5 16.5C3 18 2 19.5 2 21L6.5 19.5"/>
    <path d="M12 2C8 6 6 12 6 16.5L17.5 19.5L12 2Z"/>
    <path d="M19.5 16.5C21 18 22 19.5 22 21L17.5 19.5"/>
  </svg>`,

  hourglass: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M5 3H19"/><path d="M5 21H19"/>
    <path d="M7 3V8C7 10 9 12 12 12C15 12 17 10 17 8V3"/>
    <path d="M7 21V16C7 14 9 12 12 12C15 12 17 14 17 16V21"/>
  </svg>`,

  warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M10.29 3.86L1.82 18C1.64 18.32 1.64 18.68 1.82 19C2 19.32 2.36 19.5 2.76 19.5H21.24C21.64 19.5 22 19.32 22.18 19C22.36 18.68 22.36 18.32 22.18 18L13.71 3.86C13.53 3.54 13.18 3.36 12.76 3.36C12.36 3.36 12.06 3.54 11.88 3.86Z"/>
    <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
  </svg>`,

  globe: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
    <path d="M12 2C7 7 7 17 12 22"/><path d="M12 2C17 7 17 17 12 22"/>
  </svg>`,

  antenna: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <line x1="12" y1="2" x2="12" y2="10"/><circle cx="12" cy="2" r="1.5" fill="currentColor"/>
    <path d="M4 14C4 10 8 8 12 10"/><path d="M20 14C20 10 16 8 12 10"/>
    <line x1="4" y1="14" x2="20" y2="14"/><line x1="8" y1="14" x2="8" y2="20"/><line x1="16" y1="14" x2="16" y2="20"/><line x1="4" y1="20" x2="20" y2="20"/>
  </svg>`,

  shield: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 22C12 22 20 18 20 12V5L12 2L4 5V12C4 18 12 22 12 22Z"/>
  </svg>`,

  wrench: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M14.7 6.3a1 1 0 0 0 0 0"/>
    <path d="M21 7L17 3C15.5 1.5 13 1.5 11.5 3L3 11.5C1.5 13 1.5 15.5 3 17L7 21"/>
  </svg>`,

  xCircle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
  </svg>`,

  barChart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 3V21H21"/><rect x="7" y="10" width="4" height="8" rx="1"/><rect x="15" y="6" width="4" height="12" rx="1"/>
  </svg>`,

  thought: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 2a10 10 0 0 0 0 20a10 10 0 0 0 0-20"/>
    <circle cx="9" cy="9" r="1.5" fill="currentColor"/><circle cx="15" cy="9" r="1.5" fill="currentColor"/>
    <path d="M8 14C8.5 14.5 10 15 12 15C14 15 15.5 14.5 16 14"/>
  </svg>`,

  // 算法引擎
  engine: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="4" y="4" width="16" height="16" rx="3"/>
    <circle cx="12" cy="12" r="4"/>
    <line x1="12" y1="4" x2="12" y2="8"/>
    <line x1="12" y1="16" x2="12" y2="20"/>
    <line x1="4" y1="12" x2="8" y2="12"/>
    <line x1="16" y1="12" x2="20" y2="12"/>
    <line x1="7" y1="7" x2="9.5" y2="9.5"/>
    <line x1="14.5" y1="14.5" x2="17" y2="17"/>
    <line x1="7" y1="17" x2="9.5" y2="14.5"/>
    <line x1="14.5" y1="9.5" x2="17" y2="7"/>
  </svg>`,

  // ── 评估 / 趋势图标（替代 emoji）──
  trendUp: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>
  </svg>`,
  trendDown: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/>
  </svg>`,
  trendFlat: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="23 12 13.5 12 8.5 12 1 12"/><polyline points="17 9 23 12 17 15"/>
  </svg>`,
  moon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3A7 7 0 0 0 21 12.79Z"/>
  </svg>`,

  // AI Skills 平台图标
  skill: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>`,
  star: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  starFilled: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  download: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
  play: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
  edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`,

  // ── 扩展：去 emoji 增补（lucide 风格 · currentColor）──
  microscope: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18h8"/><path d="M3 22h18"/><path d="M14 22a7 7 0 1 0 0-14h-1"/><path d="M9 14h2"/><path d="M9 12a2 2 0 0 1-2-2V6h6v4a2 2 0 0 1-2 2Z"/><path d="M12 6V3a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v3"/></svg>`,
  scale: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>`,
  refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>`,
  zoomIn: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,
  zoomOut: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,
  link: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
  compass: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z"/><circle cx="12" cy="12" r="10"/></svg>`,
}
