
# 知识图谱海报生成工作流 (Nano-Banana 优化版)

## 1. 工作流概述

这是一套自动化的知识图谱海报生成系统，专为 **Nano Banana 2**（及其它具备强文本渲染能力的类 Flux/SDXL 模型）优化。它能够精准控制画面结构，并利用模型强大的文本渲染能力，生成图文并茂的高清手绘风格海报。

## 2. 执行步骤

### 步骤1: 获取当前材料内容

从用户提供的内容或当前画布中提取待可视化的材料。

### 步骤2: 调用 Gemini 3.0 Pro 判断内容类型

使用 **Gemini 3.0 Pro** 分析内容并返回类型编号（1-5）：

* **类型1** - 流程/步骤类 (Process/Steps)

* **类型2** - 概念解析类 (Concept Map)

* **类型3** - 对比分析类 (Comparison)

* **类型4** - 清单/工具包类 (Checklist/Resources)

* **类型5** - 综合框架/体系类 (System/Framework)

### 步骤3: 根据类型编号读取对应模板

系统自动匹配并加载下文中的 **新版结构化提示词模板**。

### 步骤4: 调用 Gemini 3.0 Pro 提取关键信息

从原始内容中提取结构化数据（标题、核心节点、列表项、数据等），准备填入模板。

### 步骤5: 用 Gemini 3.0 Pro 填充模板生成提示词

**核心策略**：采用 **"英文视觉描述 + 中文精准文本"** 的混合策略。

**指令要求**：使用 `gemini_3_pro_preview`，根据下文模板生成一段结构化的提示词（400-600词）。

* **Visual Description (英文)**：用于控制画风、构图、光影（模型对此理解更深）。

* **Text Rendering (中文)**：明确指定必须渲染的中文文字内容（格式：`text "内容"`）。

### 步骤6: 调用图片生成工具 (Nano Banana 2)

**配置参数**：

* **Model**: 使用 nano banana pro
* **模型**: 使用 nano banana pro

* **Instruction**: 使用步骤5生成的提示词

* **Aspect Ratio**: 根据模板自动选择 (`1024x1792`, `1792x1024`, `1024x1024`)

* **Guidance Scale**: **3.5 - 4.5** (Flux/Banana 类模型不宜过高)

* **Safety Tolerance**: 宽松
* **安全容错率**: 宽松

---

## 3. 模板库 (针对 Nano Banana 优化)

> **注意**：Gemini 在生成提示词时，必须严格遵守以下 `Prompt Structure`。

### 模板1：流程/步骤类

* **适用场景**：教程、指南、学习路径

* **推荐尺寸**：Portrait (1024x1792)

**Gemini 提示词生成指令**：

```text

Generate a prompt for an image generation model based on the following data:
根据以下数据生成一个用于图像生成模型的提示：

**Data:**
**数据：**

Title: {{title}}
标题：{{title}}

Subtitle: {{subtitle}}
副标题: {{subtitle}}

Steps: {{#each steps}} Step {{@index
}}: {{step_name}} - {{content}} {{/each}}
步骤: {{ #each steps}} 步骤 {{ @index }}: {{step_name}} - {{content}} {{/each}}

Highlight: {{highlight_message}}

**Prompt Structure (Write this exactly):**
**提示结构（请准确写出）：**

**1. Art Style & Medium:**
**1. 艺术风格与媒介：**

Vertical infographic poster, professional hand-drawn marker sketch style (TED visual note-taking). High definition, organic wobbly lines, Copic marker coloring style. Background is textured beige paper (#FFF8E7) to simulate a real notebook.
垂直信息图表海报，专业手绘马克笔素描风格（TED 视觉笔记）。高清，有机波浪线条，Copic 马克笔上色风格。背景是纹理米色纸（ #FFF8E7 ），模拟真实笔记本。

**2. Layout & Composition:**
**2. 布局与构图：**

A clearly defined vertical step-by-step flow chart.
一个清晰定义的垂直步骤流程图。

- Top: Large header area.
- 顶部：大型标题区域。

- Center: {{steps_count}} distinct content cards connected by hand-drawn arrows pointing downwards.
- 中间：{{steps_count}} 个不同的内容卡片，通过手绘的指向下方的箭头连接。

- Bottom: A highlighted summary box.
- 底部：一个高亮的摘要框。

**3. Text Content to Render (CRITICAL):**
**3. 要渲染的文本内容（关键）：**

Ensure the following Chinese text appears clearly and legibly in the image:
确保以下中文文本在图像中清晰可读：

- Main Title at top: text "{{title}}"
- 顶部主标题：文本 "{{title}}"

- Subtitle: text "{{subtitle}}"
- 副标题: 文本 "{{subtitle}}"

{{#each steps}}
{{ #each 步骤}}

- Step Box {{@index
}}: text "{{step_name}}"
- 步骤框 {{ @index }}: 文本 "{{step_name}}"

{{/each}}

- Footer Note: text "{{highlight_message}}"
- 页脚注释：文本 "{{highlight_message}}"

**4. Visual Details & Colors:**
**4. 视觉细节与颜色：**

- Color Palette: {{color_scheme}} (e.g., Gradient from Blue to Green).
- 色彩搭配：{{color_scheme}}（例如，从蓝色到绿色的渐变）。

- Elements: Numbered circles for each step (1, 2, 3...), distinct rounded rectangular borders for text boxes with soft drop shadows.
- 元素：每一步使用编号圆圈（1、2、3...），文本框使用独特的圆角矩形边框，并带有柔和的阴影。

- Decorations: Small doodles like stars, checkmarks, and a central icon representing {{icon_description}}.
- 装饰：星星、对勾等小涂鸦，以及一个代表{{icon_description}}的中心图标。

模板2：概念解析类

适用场景：思维导图、核心概念拆解

推荐尺寸：Square (1024x1024)

Gemini 提示词生成指令：

code

Text
文本

download
下载

content_copy
复制内容

expand_less
收起

Generate a prompt for an image generation model based on the following data:
根据以下数据生成一个用于图像生成模型的提示：

**Data:**
**数据：**

Core Concept: {{core_concept}}
核心概念：{{core_concept}}

Dimensions: {{#each dimensions}} {{name}} {{/each}}
尺寸：{{ #each 尺寸}} {{name}} {{/each}}

Center Icon: {{center_icon}}
中心图标：{{center_icon}}

**Prompt Structure (Write this exactly):**
**提示结构（请准确写出）：**

**1. Art Style & Medium:**
**1. 艺术风格与媒介：**

Square mind-map illustration, hand-drawn sketch style. Clean lines, vibrant marker colors on off-white paper texture. Visual recording style.
方形思维导图插图，手绘草图风格。线条干净，在浅白色纸张纹理上使用鲜艳的标记颜色。视觉记录风格。

**2. Layout & Composition:**
**2. 布局与构图：**

Centralized Radial Composition.
中心辐射式构图。

- Center: A large, prominent central node (circle or cloud shape).
- 中心：一个大型、突出的中心节点（圆形或云朵形状）。

- Surrounding: {{dimensions_count}} branches radiating outward evenly. Each branch connects to a secondary node/box.
- 周围：{{dimensions_count}} 个分支均匀向外辐射。每个分支连接到一个次级节点/盒子。

**3. Text Content to Render (CRITICAL):**
**3. 要渲染的文本内容（关键）：**

Ensure the following Chinese text appears clearly:
确保以下中文文本清晰显示：

- Center Node: text "{{core_concept}}"
- 中心节点：文本 "{{core_concept}}"

{{#each dimensions}}
{{ #each 维度}}

- Branch Node: text "{{name}}"
- 分支节点：文本 "{{name}}"

{{/each}}

**4. Visual Details & Colors:**
**4. 视觉细节与颜色：**

- Color Palette: Central node in {{center_color}}, surrounding nodes in varied warm/cool tones to distinguish categories.
- 配色方案：中心节点为{{center_color}}，外围节点采用不同的暖色/冷色调以区分类别。

- Connectors: Hand-drawn curved lines or arrows connecting the center to the outer nodes.
- 连接线：手绘的曲线或箭头连接中心节点与外围节点。

- Icons: Simple hand-drawn icons ({{center_icon}}) inside the central node.
- 图标：中心节点内包含简单的手绘图标（{{center_icon}}）。

模板3：对比分析类

适用场景：产品对比、优劣势分析 (VS)

推荐尺寸：Landscape (1792x1024)

Gemini 提示词生成指令：

code

Text
文本

download
下载

content_copy
复制内容

expand_less
收起

Generate a prompt for an image generation model based on the following data:
根据以下数据生成一个用于图像生成模型的提示：

**Data:**
**数据：**

Title: {{title}}
标题：{{title}}

Side A: {{side_a_title}} (Color: {{color_a}})
A 面：{{side_a_title}} (颜色：{{color_a}})

Side B: {{side_b_title}} (Color: {{color_b}})
B 面：{{side_b_title}} (颜色：{{color_b}})

Conclusion: {{conclusion}}
结论：{{conclusion}}

**Prompt Structure (Write this exactly):**
**提示结构（请准确写出）：**

**1. Art Style & Medium:**
**1. 艺术风格与媒介：**

Wide landscape comparison poster, split-screen layout. Hand-drawn whiteboard sketch style. Marker pens on paper texture.
宽屏风景对比海报，分屏布局。手绘白板草图风格。纸面马克笔纹理。

**2. Layout & Composition:**
**2. 布局与构图：**

Symmetrical Split Layout.
对称分割布局。

- Top: Title spanning the width.
- 顶部：标题跨越整个宽度。

- Middle: Divided vertically by a "VS" or lightning bolt line.
- 中间：由“VS”或闪电形线条垂直分割。

- Left Side: Represents {{side_a_title}}, using rounded panels.
- 左侧：代表{{side_a_title}}，使用圆角面板。

- Right Side: Represents {{side_b_title}}, using rounded panels.
- 右侧：代表{{side_b_title}}，使用圆角面板。

- Bottom: A wide banner for the conclusion.
- 底部：一个宽横幅用于结论。

**3. Text Content to Render (CRITICAL):**
**3. 要渲染的文本内容（关键）：**

Ensure the following Chinese text appears clearly:
确保以下中文文本清晰显示：

- Main Title: text "{{title}}"
- 主标题：text "{{title}}"

- Left Header: text "{{side_a_title}}"
- 左侧标题：文本 "{{side_a_title}}"

- Right Header: text "{{side_b_title}}"
- 右侧标题：文本 "{{side_b_title}}"

- Center Divider: text "VS"
- 中心分隔符：文字"VS"

- Bottom Conclusion: text "{{conclusion}}"
- 底部结论：文字"{{conclusion}}"

**4. Visual Details & Colors:**
**4. 视觉细节与颜色：**

- Color Palette: Strong contrast. Left side uses {{color_a}} tones; Right side uses {{color_b}} tones.
- 色彩搭配：强烈对比。左侧使用{{color_a}}色调；右侧使用{{color_b}}色调。

- Elements: Checkmarks (✔️) on the positive side, Crosses (❌) or different bullets on the other.
- 元素：正面使用勾选标记（ ✔️ ），反面使用叉号（ ❌ ）或不同的圆点。

- Background: Clean paper texture (#FFF8E7).
- 背景：干净的纸张纹理（ #FFF8E7 ）。

模板4：清单/工具包类

适用场景：资源列表、工具推荐、检查表

推荐尺寸：Portrait (1024x1792)

Gemini 提示词生成指令：

code

Text
文本

download
下载

content_copy
复制内容

expand_less
收起

Generate a prompt for an image generation model based on the following data:
根据以下数据生成一个用于图像生成模型的提示：

**Data:**
**数据：**

Title: {{title}}
标题：{{title}}

Categories: {{#each categories}} {{category_name}} {{/each}}
分类：{{ #each categories}} {{category_name}} {{/each}}

Bottom Note: {{bottom_note}}
底部注释：{{bottom_note}}

**Prompt Structure (Write this exactly):**
**提示结构（请准确写出）：**

**1. Art Style & Medium:**
**1. 艺术风格与媒介：**

Vertical checklist or cheat-sheet poster. Hand-drawn infographic style. Neat, organized, and highly legible.
垂直清单或小册子海报。手绘信息图表风格。整洁、有序且高度易读。

**2. Layout & Composition:**
**2. 布局与构图：**

Grid or List Layout.
网格或列表布局。

- Header: Bold title at the top with a tool icon.
- 头部：顶部有加粗标题和工具图标。

- Body: Divided into distinct sections/cards for each category. Inside each card is a bulleted list.
- 主体：分为不同的区域/卡片，每个类别一个。每个卡片内是项目符号列表。

- Footer: A highlighted action box.
- 底部：一个突出显示的操作框。

**3. Text Content to Render (CRITICAL):**
**3. 要渲染的文本内容（关键）：**

Ensure the following Chinese text appears clearly:
确保以下中文文本清晰显示：

- Title: text "{{title}}"
- 标题：text "{{title}}"

{{#each categories}}

- Section Header: text "{{category_name}}"
- 标题区域：文本 "{{category_name}}"

{{/each}}

- Footer: text "{{bottom_note}}"
- 页脚：文本 "{{bottom_note}}"

**4. Visual Details & Colors:**
**4. 视觉细节与颜色：**

- Color Palette: Multicolored sections (Rainbow or Pastel colors) to differentiate categories.
- 配色方案：使用多色区域（彩虹色或柔和色调）来区分类别。

- Elements: Checkboxes (☑️) or bullet points before each item line. Hand-drawn frames around each section.
- 元素：每个项目行前使用复选框（ ☑️ ）或项目符号。每个区域周围使用手绘边框。

- Atmosphere: Productive and useful toolset vibe.
- 氛围：高效实用的工具集感觉。

模板5：综合框架/体系类

适用场景：宏观架构、系统图、知识体系

推荐尺寸：Landscape (1792x1024)

Gemini 提示词生成指令：

code

Text
文本

download
下载

content_copy
复制内容

expand_less
收起

Generate a prompt for an image generation model based on the following data:
根据以下数据生成一个用于图像生成模型的提示：

**Data:**
**数据：**

Title: {{title}}
标题：{{title}}

Main Sections: {{#each major_sections}} {{section_name}} {{/each}}
主要部分：{{ #each major_sections}} {{section_name}} {{/each}}

Center Theme: {{theme}}
中心主题：{{theme}}

**Prompt Structure (Write this exactly):**
**提示结构（请准确写出）：**

**1. Art Style & Medium:**
**1. 艺术风格与媒介：**

Wide landscape system architecture diagram. Hand-drawn sketch style, similar to a "Napkin sketch" or whiteboard strategy session. Complex but organized.
广阔的风景系统架构图。手绘草图风格，类似于“餐巾纸草图”或白板策略会话。复杂但有条理。

**2. Layout & Composition:**
**2. 布局与构图：**

Holistic Framework Layout.
整体框架布局。

- A large encompassing shape (circle or rectangle) holding all elements.
- 一个大的包含形状（圆形或矩形）包含所有元素。

- Divided into {{structure_type}} distinct zones or pillars.
- 分为 {{structure_type}} 个不同的区域或支柱。

- Arrows indicating flow or relationships between zones.
- 指示区域之间流程或关系的箭头。

**3. Text Content to Render (CRITICAL):**
**3. 要渲染的文本内容（关键）：**

Ensure the following Chinese text appears clearly:
确保以下中文文本清晰显示：

- Main Title: text "{{title}}"
- 主标题：text "{{title}}"

- Center/Core Text: text "{{theme}}"
- 中心/核心文本：文本 "{{theme}}"

{{#each major_sections}}

- Zone Label: text "{{section_name}}"
- 区域标签：文本 "{{section_name}}"

{{/each}}

**4. Visual Details & Colors:**
**4. 视觉细节与颜色：**

- Color Palette: Professional business colors (Blues, Greys, with Orange/Gold accents for key insights).
- 色彩搭配：专业的商务色彩（蓝色、灰色，关键洞察处用橙色/金色点缀）。

- Elements: Icons representing strategy, technology, and growth. Dotted lines for connections.
- 元素：代表策略、技术和增长的图标。用虚线表示连接。

- Shadows: Drop shadows to give depth to the layers.
- 阴影：使用投影阴影为各层增加深度。

4. 配置参数说明 (供 Gemini 填充参考)

配色方案 (Color Palettes)

warm: "Warm color palette (Orange, Yellow, Teal), friendly and approachable."
暖色：暖色调（橙色、黄色、蓝绿色），友好且易于接近。

cool: "Cool color palette (Blue, Purple, Grey), professional and tech-focused."
冷色：冷色调（蓝色、紫色、灰色），专业且以科技为中心。

vibrant: "Vibrant high-saturation colors (Bright Orange, Neon Green), energetic and creative."
鲜艳色：鲜艳的高饱和度颜色（亮橙色、霓虹绿），充满活力且富有创意。

classic: "Classic muted colors (Navy Blue, Dark Red, Gold), trustworthy and authoritative."
经典色：经典的柔和颜色（海军蓝、深红色、金色），值得信赖且具有权威性。

尺寸自动匹配逻辑

内容类型 推荐尺寸 分辨率

流程步骤 / 清单工具 Portrait 1024x1792

对比分析 / 综合框架 Landscape 1792x1024

概念解析 Square 1024x1024