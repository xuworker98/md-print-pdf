# Third-Party Notices

本仓库包含以下第三方组件，特此声明其许可信息。除下述目录外，本仓库其余代码与文档均适用仓库根目录的 MIT 许可证。

---

## 1. KaTeX（`assets/katex/`）

- **来源**：<https://github.com/KaTeX/KaTeX>
- **版本**：0.16.x 系列离线快照（含 `katex.min.js`、`katex.min.css`、`contrib/` 与 `fonts/`）
- **用途**：Markdown 中 `$...$` / `$$...$$` 数学公式的离线渲染
- **许可**：MIT License

> Copyright (c) 2013-2020 Khan Academy and other contributors
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

## 2. 运行时依赖（不入库、由运行环境提供）

| 组件 | 许可 | 说明 |
|---|---|---|
| Microsoft Edge / Google Chrome | 各自专有许可 | 渲染内核，经 playwright-core 驱动，本仓库不分发其任何文件 |
| playwright-core | Apache-2.0 | Node 侧自动化库，用户自行安装，本仓库不分发 |
| Node.js / Python | MIT / PSF | 运行时环境 |
