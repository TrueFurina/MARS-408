// PostCSS 配置 — 自动补全浏览器前缀（autoprefixer）
// 配合 package.json 的 browserslist 声明目标浏览器范围
// Vite 构建时自动读取本文件，对所有 CSS（含 Vue SFC <style>）补全 -webkit-/-moz- 等前缀
export default {
  plugins: {
    autoprefixer: {},
  },
}
