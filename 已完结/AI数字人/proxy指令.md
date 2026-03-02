
只紧随其后运行的那一条命令生效，
    HTTPS_PROXY="http://10.30.44.154:7897" HTTP_PROXY="http://10.30.44.154:7897" git clone https://github.com/openai/CLIP.git

当前这一个窗口（会话）一直走代理-直接修改就是覆盖
    export HTTP_PROXY="http://10.30.44.154:666"
    export HTTPS_PROXY="http://10.30.44.154:666"

    export HTTP_PROXY="http://10.30.44.154:7897"
    export HTTPS_PROXY="http://10.30.44.154:7897"


    export HTTP_PROXY="http://10.30.43.34:7897"
    export HTTPS_PROXY="http://10.30.43.34:7897"


python inference.py --data_root "./checkpoints/ditto_pytorch" --cfg_pkl "./checkpoints/ditto_cfg/v0.4_hubert_cfg_pytorch.pkl" --audio_path "./mydata/120701.WAV" --source_path "./mydata/120801.png" --output_path "./mydata/result_4090.mp4"


使用 gitclone.com (老牌加速)
    git clone https://gitclone.com/github.com/comfyanonymous/ComfyUI.git
    git clone https://github.com/comfyanonymous/ComfyUI.git


    cd custom_nodes
    git clone https://gitclone.com/github.com/ltdrdata/ComfyUI-Manager.git
    cd ..