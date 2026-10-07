import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'

export default [
  {
    name: 'app/ignore',
    ignores: [
      'dist',
      'node_modules',
      'public',
      'archive',
      'coverage',
      'eslint.config.js',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    name: 'app/vue-parser',
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
  {
    // Node 运行时脚本（scripts/*.mjs 等）与顶层配置文件运行在 Node 环境，
    // 需要 process/Buffer 等 Node 全局；覆盖 **/*.mjs/**/*.cjs 与 scripts/*.config.*，
    // 避免把 Node 全局泄漏给 src/ 下的浏览器端代码（否则误用不再被 no-undef 拦截）。
    // 显式声明而不 import `globals` 包：后者目前只是 eslint 的传递依赖，
    // 一旦写进 package.json 而未同步 package-lock.json，`npm ci` 会因两者不同步直接失败。
    name: 'app/node-scripts',
    files: ['**/*.mjs', '**/*.cjs', 'scripts/**/*.js', '*.config.js', '*.config.ts', '*.config.mjs'],
    languageOptions: {
      globals: {
        process: 'readonly',
        console: 'readonly',
        Buffer: 'readonly',
        __dirname: 'readonly',
        __filename: 'readonly',
        require: 'readonly',
        module: 'writable',
        exports: 'writable',
        global: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        setImmediate: 'readonly',
        clearImmediate: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        TextEncoder: 'readonly',
        TextDecoder: 'readonly',
      },
    },
  },
  {
    name: 'app/rules',
    rules: {
      // 与后端 API 契约宽松对接，项目大量使用 any，不阻断
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
      '@typescript-eslint/ban-ts-comment': 'off',
      '@typescript-eslint/ban-types': 'off',
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      '@typescript-eslint/no-empty-function': 'off',
      '@typescript-eslint/no-unused-expressions': 'off',
      'vue/no-parsing-error': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // SPA 单文件组件命名（ChatView / AppView 等）放宽
      'vue/multi-word-component-names': 'off',
      // 已统一用 DOMPurify 净化所有 v-html
      'vue/no-v-html': 'off',
      'vue/require-default-prop': 'off',
      'vue/no-setup-props-destructure': 'off',
      'no-console': 'off',
      'prefer-const': 'warn',
      'no-empty': 'off',
    },
  },
]
