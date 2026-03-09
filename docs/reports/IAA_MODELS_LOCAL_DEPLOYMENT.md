# Modern Image Aesthetic Quality Assessment Models (Local Deployment Ready)
*Converted from PDF: Modern Image Aesthetic Quality Assessment Models (Local Deployment Ready).pdf*

## Page 1

Modern Image Aesthetic Quality Assessment
Models (Local Deployment Ready)
Overview:Image aesthetic assessment (IAA) models predict how aesthetically pleasing an image is, typically
on datasets like AVA (photographic aesthetics) or others. Two well-known models are MUSIQ (ICCV 2021)
and  LIQE (CVPR 2023). MUSIQ introduced a multi-scale vision transformer that set state-of-art results on
technical quality datasets and achieved strong (though not absolute best) performance on AVA.
LIQE  leveraged  vision-language  multitask  learning  (with  CLIP  features)  to  advance  no-reference  image
quality prediction, outperforming prior IQA methods on multiple benchmarks. On AVA (aesthetic) data,
LIQE also improved accuracy (≈0.776 SRCC) beyond MUSIQ’s ~0.726. The field has since seen  newer
models that further boost aesthetic scoring accuracy. Below, we detail several top-performing models
(all compatible with local PyTorch or TensorFlow implementations) which outperform or build upon MUSIQ
and LIQE, along with their main datasets and available code/checkpoints.
TANet (IJCAI 2022) – Theme-Aware Aesthetic Network
Framework: PyTorch (official code on GitHub)
Datasets: AVA, FLICKR-AES, TAD66K (new 66K-image dataset with 47 themes)
Description:TANet was introduced as part of a comprehensive study on image aesthetics. It tackles
the fact that different image  themes (e.g. portrait, landscape, etc.) affect aesthetic criteria. TANet uses a
two-branch CNN: a  TUNet to extract theme information and an  adaptive perception module to apply
theme-specific aesthetic rules. This approach improved prediction by accounting for image content
variations.  TANet  achieved  state-of-the-art results  on  AVA,  Flickr-AES  and  the  new  TAD66K  dataset,
surpassing earlier methods (e.g. NIMA, MUSIQ) on all three. On AVA its rank correlation ~0.758 edged
out MUSIQ .  Implementation: The authors provide PyTorch training code and pretrained weights for
TANet and the TAD66K dataset on GitHub (enabling local evaluation on an RTX 4060). 
Note: Another 2022 approach, GAT+GATP (Graph Attention Network ensemble), similarly attained
~0.762 SRCC on AVA by modeling image regions as graph nodes. This indicates graph-based
feature aggregation can also yield high aesthetic accuracy.
VILA (CVPR 2023) – Vision-Language Pretrained Aesthetic Model
Framework: TensorFlow (Google Research code; image model can be used in PyTorch)
Datasets: AVA (aesthetics), AVA-Captions (image+comment pairs), personal aesthetics datasets
Description:VILA (“Vision and  Language Aesthetics”) is a multimodal model that learns aesthetics from
user comments in addition to images. Instead of relying solely on mean opinion scores, VILA pretrains
an image–text encoder-decoder on a large set of images paired with human comments about aesthetics
. This learns rich aesthetic semantics (composition, style, etc.) beyond numeric ratings. A small  rank-
based adapter is then fine-tuned on AVA to predict aesthetic scores. With this strategy, VILA achieved
state-of-the-art performance on AVA – after minimal fine-tuning it reached an SRCC of ~0.774 on AVA,
tying/outperforming prior SOTAs like TANet. It also demonstrated strong zero-shot abilities (e.g. style
classification).

## Page 2

classification). Implementation: The official code (by Google) is available, and the image branch of VILA
(for score prediction) can be run locally. Using the released model, an RTX 4060 can infer aesthetic
scores from images alone (no need for input text during inference). 
LIQE (CVPR 2023) – Language-Image Quality Evaluator
Framework: PyTorch (official GitHub repository)
Datasets: KonIQ-10k, SPAQ, CSIQ, etc. (IQA datasets); tested cross-domain on AVA
Description:LIQE is a no-reference image quality model that exploits vision-language correspondence to
boost performance . It uses a CLIP-based backbone: image features from CLIP are combined with
text  embeddings  of  various  “auxiliary”  labels  (scene  category,  distortion  type)  via  a  multitask  learning
scheme . By jointly training on multiple tasks and using carefully designed losses, LIQE learns a rich
representation that improves quality prediction. It outperforms previous state-of-the-art BIQA models on
numerous technical quality benchmarks. Importantly, although designed for technical image quality,
LIQE’s robust features also translate well to aesthetics – when evaluated on AVA (after training on aesthetic
data), it achieved ~0.776 SRCC, slightly above TANet/VILA. Implementation: The authors provide PyTorch
code and pretrained weights, and LIQE can run efficiently on a single GPU (uses CLIP ViT-B/16 by
default). In practice, it can score a local image in a single forward pass (inference speed similar to CLIP). 
Q-Align (ArXiv 2023) – LMM-Based Aesthetic Rating Alignment
Framework: PyTorch (leverages large vision-language models; research prototype)
Datasets: AVA (aesthetics), KonIQ, SPAQ, etc. – combined training across 5 datasets
Description:Q-Align (Wu et al., 2023) takes a novel approach by fine-tuning a Large Multimodal Model
(LMM) to  output  visual  quality  scores.  It  uses  instruction-tuned  vision-language  models  (like  BLIP/
InstructBLIP with a language decoder) and “aligns” their output to discrete rating levels (Excellent, Good,
Fair , Poor , Bad) instead of raw scores. This leverages the LMM’s strength in understanding human-like
descriptors . Through a special training syllabus converting MOS scores to text levels and back
, Q-Align teaches the LMM to predict ratings accurately. The result is significantly improved aesthetic
scoring – Q-Align reached SRCC ≈0.822 on AVA , outperforming all prior purely-visual models (MUSIQ,
LIQE, VILA) by a clear margin. It even surpasses LIQE by ~7% and the LAION CLIP-based aesthetic predictor
by ~10% in correlation. Notably, Q-Align achieved those gains using the same data, albeit at the cost of
a large model (~1B+ parameters).  Implementation: While Q-Align is a research concept (no official
release yet), it can be reproduced with open LMMs (e.g. LLaVA or InstructBLIP). Running such a model
locally on an RTX 4060 is feasible with model pruning/quantization, but inference speed will be slower and
memory usage high (relative to smaller CNN/ViT models). For instance, using a 7B-parameter LMM in 8-bit
precision may just fit in 8 GB VRAM. Q-Align represents a trade-off: top-notch accuracy at the expense of
heavier resources.
QPT V2 (ACM MM 2024) – Quality & Aesthetics Pre-training (Masked
Modeling)
Framework: PyTorch (code and checkpoints released)
Datasets: Unlabeled pretraining on 1M+ images (SA-1B, Unsplash etc.); fine-tuned on AVA, KonIQ-10k,
SPAQ, etc.
Description:QPT V2  is a unified pre-training framework that achieves state-of-the-art results across

## Page 3

both image  aesthetic  assessment  and  technical  quality  assessment.  It  builds  on  the  idea  of  self-
supervised Masked Image Modeling (MIM) (à la MAE/BEiT) to learn representations sensitive to both high-
level  aesthetics  and  low-level  quality  factors.  QPT  V2  introduces  three  key  innovations  during
pretraining : (1) A curated high-resolution image corpus with diverse content for learning semantics
and  distortions,  (2)  custom  degradation  augmentation (color  transforms,  blur ,  noise,  etc.)  applied  to
images to imbue quality-awareness, and (3) a hierarchical Vision Transformer (HiViT-T backbone with ~19M
params) that includes a multi-scale feature fusion module. After this pretraining, the model is fine-tuned
on specific datasets (AVA, KonIQ, etc.) for scoring. QPT V2 now leads the field on AVA, reporting SRCC =
0.865 and PLCC = 0.875 on AVA’s test set – a sizable jump (+9% SRCC) over previous best visual models
(LIQE/VILA ~0.77). Notably, it even outperforms the LMM-based Q-Align by a wide margin, while
using  a  much  smaller  model  and  less  computation.  This  makes  QPT  V2  highly  attractive  for  local
deployment.  Implementation: The authors have released PyTorch code and intend to provide pretrained
weights . With a HiViT-T backbone (~19M parameters), QPT V2 is lightweight – an RTX 4060 can easily
handle inference (and even fine-tuning) with modest VRAM. Inference is fast (just a single forward pass
without needing multiple crops or multi-scale ensembles, thanks to the learned multi-scale features). 
AesMamba (ACM MM 2024) – Universal Aesthetic Assessment via
State-Space Models
Framework: PyTorch (research code under review; planned release)
Datasets: Multiple: AVA, TAD66K, AADB (generic aesthetics); PARA (attribute-specific aesthetics); personal
aesthetic datasets (user-specific preferences)
Description:AesMamba is a modular framework aiming for a  “universal” solution to image aesthetics –
covering generic aesthetics, fine-grained attributes, and even personalized aesthetics. Instead of
standard CNNs or ViTs, AesMamba employs a Visual State-Space Model (dubbed VMamba) as the image
backbone . State-space models (SSMs) can capture both global and local image information efficiently,
which AesMamba leverages for aesthetic representation. The framework then adapts to various IAA tasks
via different modules: a modal-adaptive module to integrate vision & text inputs (for multimodal cases), a
multitask balanced adaptation to boost learning of under-represented aesthetic attributes, and even a
prompt-based approach to include user preference traits for personalized scoring. In evaluations,
AesMamba showed  competitive or superior performance across the board. For example, its visual-
only model (AesMamba-V) reached ~0.75 SRCC on AVA – on par with MUSIQ and just shy of LIQE/VILA
 – while  outperforming prior art on other datasets like AADB and the fine-grained PARA benchmark
(where it hit 0.902 SRCC on overall aesthetic quality). The multimodal variant (AesMamba-M, using
image + text comments) further boosted results, exceeding VILA’s performance by substantial margins
.  Implementation: The authors report that AesMamba is fairly lightweight (the core VMamba model in
Tiny configuration has ≈20M params) and optimizable for real-time use. The code and pre-trained
models  are  to  be  released;  once  available,  they  should  run  on  local  GPUs.  The  expected  PyTorch
implementation will allow inference on a single image for generic aesthetics, or even multi-input scenarios
(for personalized or multimodal assessment) on a machine like an RTX 4060.
<br>
Summary – Performance on AVA (Aesthetic Prediction): The table below compares key models on the
AVA benchmark for image aesthetics. We report Spearman’s rank correlation (SRCC) between predicted
scores and human ratings (higher is better), as reported in the literature:
## Page 4

| Model | Year | Framework | AVA SRCC (↑) | Source |
|-------|------|-----------|--------------|--------|
| NIMA (CNN) | 2018 | TensorFlow | 0.612 | Talebi & Milanfar, 2018 |
| MLSP (multi-patch) | 2019 | Caffe/PyTorch | 0.756 | Hosu et al., 2019 |
| MUSIQ (Transformer) | 2021 | TensorFlow | 0.726 | Ke et al., ICCV 2021 |
| TANet (theme-aware) | 2022 | PyTorch | 0.758 | He et al., IJCAI 2022 |
| GAT+GATP (Graph Attn) | 2022 | PyTorch | 0.762 | Ghosal & Smolic, ICPR 2022 |
| LIQE (CLIP-based) | 2023 | PyTorch | 0.776 | Zhang et al., CVPR 2023 |
| VILA (vision-lang.) | 2023 | TensorFlow | 0.774 | Ke et al., CVPR 2023 |
| LAION CLIP predictor | 2023 | PyTorch | 0.721 | LAION (Kaggle model) |
| Q-Align (LMM-based) | 2023 | PyTorch | 0.822 | Wu et al., 2023 (arXiv) |
| **QPT V2 (HiViT-MIM)** | **2024** | **PyTorch** | **0.865** | Xie et al., ACM MM 2024 |
| AesMamba-V (SSM) | 2024 | PyTorch | 0.751 | Wang et al., ACM MM 2024 |
*Trends in aesthetic score prediction on AVA.* Early methods like NIMA improved to ~0.63 SRCC. By 2021–2022,
MUSIQ and  TANet pushed correlations into the mid-0.7s.  LIQE (2023) broke the 0.77
barrier ,  and  vision-language  models  like  VILA reached  similar  levels.  The  latest
approaches have made a leap:  Q-Align crossed 0.82  by harnessing large multimodal
models, and  QPT V2 now sets the record at ~0.865 using efficient masked pretraining.
These newer models offer notably higher accuracy for aesthetic prediction, while remaining
deployable on local GPUs (with QPT V2 being especially lightweight and practical for an RTX
4060).

### References

- MUSIQ: Assessing Image Aesthetic and Technical Quality with Multi-scale Transformers
https://research.google/blog/musiq-assessing-image-aesthetic-and-technical-quality-with-multi-scale-transformers/
QPT V2: Masked Image Modeling
Advances Visual Scoring
https://arxiv.org/html/2407.16541v1
GitHub - zwx8981/LIQE: [CVPR2023] Blind Image Quality Assessment via Vision-
Language Correspondence: A Multitask Learning Perspective
https://github.com/zwx8981/LIQE
Rethinking Image Aesthetics Assessment: Models, Datasets and Benchmarks | IJCAI
https://www.ijcai.org/proceedings/2022/132
[Quick Review] Rethinking Image Aesthetics Assessment: Models ...
https://liner.com/review/rethinking-image-aesthetics-assessment-models-datasets-and-benchmarks

## Page 5

AesMamba: Universal Image Aesthetic
Assessment with State Space Models
https://openreview.net/pdf/543adc6f9b435ea008314023d5b6e394bbd4f875.pdf
Image Aesthetics Assessment Using Graph Attention Network ...
https://www.researchgate.net/publication/365843934_Image_Aesthetics_Assessment_Using_Graph_Attention_Network
Google | vila - Kaggle
https://www.kaggle.com/models/google/vila
[PDF] VILA: Learning Image Aesthetics from User Comments with ...
https://www.semanticscholar .org/paper/d7c1f382fc3aa5e8da9fcad94f30c6dc1f8eb3f8
[2303.14302] VILA: Learning Image Aesthetics from User Comments with Vision-Language
Pretraining
https://arxiv.org/abs/2303.14302
Q-Align: Teaching LMMs for Visual Scoring via Discrete Text-Defined Levels
https://arxiv.org/html/2312.17090v1
GitHub - KeiChiTse/QPT-V2: [ACM MM 2024] QPT V2: An MIM-based pretraining framework for
IQA, VQA, and IAA.
https://github.com/KeiChiTse/QPT-V2
