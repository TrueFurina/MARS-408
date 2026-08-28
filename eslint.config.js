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
