 👀 先看效果再装
官方预览页，每个主题都有截图：
👉 starship.rs/presets

这是指令：starship preset pastel-powerline -o ~/.config/starship.toml

问题是 Starship 在 Windows 上路径解析有点问题。用完整路径

starship preset pastel-powerline -o "$env:USERPROFILE\.config\starship.toml"