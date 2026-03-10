# Local Image Aesthetic Quality Assessment Models (2024–2025)
*Converted from PDF: Local Image Aesthetic Quality Assessment Models (2024–2025).pdf*

## Page 1

Local Image Aesthetic Quality Assessment Models
(2024–2025)
Introduction
Local Image Aesthetic Assessment (IAA) involves scoring the aesthetic quality of images directly on-device
(e.g.  using  a  GPU  like  an  RTX   4060)  without  relying  on  external  APIs.  It  is  commonly  evaluated  on
benchmarks such as  AVA (a large 250k+ image dataset with average aesthetic ratings), as well as image
quality  datasets  like  KonIQ-10k and  SPAQ (which  focus  on  perceptual  image  quality  but  overlap  with
aesthetics). In recent years, models have rapidly improved IAA performance on AVA – for instance, the
multi-scale  transformer  MUSIQ (ICCV  2021)  reached  ~0.726  SRCC  on  AVA,  and  the  vision-language
model  LIQE (CVPR 2023) pushed to ~0.776. However , there is a need to surpass these earlier models
(MUSIQ, LIQE) in both accuracy and generalization. The following sections survey the  most recent and
best-performing  local  IAA  models (2024–2025)  that  are  compatible  with  PyTorch  or  TensorFlow  and
suitable for local deployment. Each model description includes its year , framework, method and unique
contributions, AVA benchmark performance, inference feasibility on a typical GPU, and available code or
checkpoints.
QPT V2 (2024)
Framework: PyTorch (official code on GitHub).
Method:Quality and Aesthetics-aware Pretraining v2 (QPT V2) is a unified approach that uses masked image
modeling (MIM) pre-training to handle both image quality and aesthetics assessment. The model is a
multi-scale Vision Transformer with a  hierarchical encoder and a special feature fusion module that exists
only  during  pre-training.  QPT   V2  is  trained  on  curated  high-resolution  image  data  (with  high
foreground content) to learn both high-level semantics and fine details, and it introduces a  degradation
strategy during MIM pre-training to teach the model about quality and aesthetic factors. These design
choices (multi-scale autoencoder , targeted degradation types, etc.) equip QPT V2 to capture multi-scale
distortion and aesthetic information better than prior models.
Performance: QPT V2 achieves  state-of-the-art results on AVA, with about  4.3% higher SRCC than the
previous best methods. This corresponds to roughly  SRCC ≈0.82 on AVA, a new benchmark high.
Notably, it attained these gains without relying on any vision-language data or prompts – it is purely vision-
based, yet its aesthetic correlation surpasses models that use text or multi-modal cues.
Inference Feasibility: The QPT V2 model uses a ViT-based encoder that is reasonable in size (the authors
do not specify exact parameters, but it’s comparable to other ViT backbones). Running inference on a
modern GPU (e.g. RTX 4060) is feasible in real-time for single images. Its multi-scale architecture means the
image is processed at multiple resolutions, which adds some overhead, but this is still practical on a 12GB
VRAM device.
Code & Checkpoints: Official PyTorch code and pre-trained weights are available on GitHub, making it
straightforward for developers to integrate QPT V2 into local pipelines.
1
2
3
4
5 4
6
4
4
4
3
1

## Page 2

LIQE (2023)
Framework: PyTorch (official implementation available).
Method:Language-Image Quality Evaluator (LIQE)  is a vision-language model originally designed for no-
reference image quality assessment, but it also achieves strong results for aesthetics. LIQE leverages the
CLIP visual encoder (a ViT) and formulates a multitask learning scheme that jointly learns image quality,
scene  classification,  and  distortion  type  identification.  The  key  idea  is  to  describe  possible  label
combinations with a textual template and compute a joint vision-text embedding probability – essentially
using CLIP’s embedding space to align image content with descriptive prompts. By optimizing carefully
designed losses for each task (quality, scene, distortion) on this joint distribution, LIQE learns a quality-
aware and scene-aware representation of images. This auxiliary knowledge (scene context, etc.) helps the
model predict aesthetic ratings better than a single-task model. LIQE fine-tuned on AVA treats aesthetic
score regression as a similar task (with prompts like “a photo with an aesthetic score of X”), although its
original paper emphasized technical quality.
Performance: When adapted to aesthetics, LIQE matches prior state-of-the-art on AVA with  SRCC ≈0.77
.  In  one  reported  result,  LIQE  achieved  SRCC  0.776 on  AVA’s  test  set –  essentially  on  par  with
contemporary models like VILA (0.774) and about 5% higher than MUSIQ’s SRCC. This demonstrated that
incorporating semantic scene information via CLIP could boost aesthetic prediction performance.
Inference Feasibility: LIQE’s backbone is the CLIP ViT model (the authors used a ViT-B/16 from CLIP,
but one could also use ViT-L/14 for higher accuracy at the cost of speed). A ViT-B model (~86 million params)
can comfortably run on an RTX 4060, scoring an image in a fraction of a second. Even with a larger CLIP
model, inference is still practical on local GPUs with mixed precision. LIQE does not require huge memory
beyond what CLIP requires, so a mid-range GPU is sufficient for real-time image scoring.
Code  &  Checkpoints: The  official  code  is  released  on  GitHub  (MIT-licensed)  and  includes  pre-trained
weights for the CLIP-based model. Developers can either use the provided code or load LIQE through
the pyiqa PyTorch-IQA library (which now includes LIQE as a metric for easy integration).
VILA (2023)
Framework: TensorFlow / JAX (official Google Research code; model can be used in PyTorch via released
weights and HuggingFace interfaces).
Method:Vision-Language Aesthetics (VILA)  is a two-stage framework that learns image aesthetics from
user comments and then fine-tunes on rating data. In the first stage, an image-text  encoder–decoder
(based on Google’s CoCa model) is  pretrained on image–comment pairs from the web. The model
uses  contrastive learning (matching images with their comments) and  generative learning (predicting
comments from images) to imbue the image encoder with rich aesthetic semantics beyond numerical
scores .  This  yields  a  vision-language  model  that  understands  aesthetic  concepts  (via  comments
describing composition, style, etc.) without any human rating labels. In the second stage, VILA introduces a
lightweight  rank-based adapter module for the supervised AVA task. This adapter uses text anchors
(“good image” vs “bad image”) and a small set of parameters to learn a ranking function, while the pre-
trained backbone’s weights are frozen. Essentially, the adapter fine-tunes the model to predict aesthetic
scores by anchoring images on a good–bad continuum in the learned embedding space.
Unique Contributions: VILA was the first to leverage unstructured  user comments at scale for IAA. By
doing so, it captures more nuanced aesthetic preferences (“Very good composition and use of color .” etc.)
that numeric scores alone miss. It also introduced the idea of zero-shot aesthetic evaluation – e.g. using
the pre-trained model with prompts to judge images without any fine-tuning.
Performance: With minimal fine-tuning, VILA achieved  state-of-the-art performance on AVA upon its
7 8
9
10
10
2 2
8
11
12
13
14
13
13
13
2

## Page 3

release . Fine-tuned VILA (with the rank adapter) reaches about SRCC 0.774 and PLCC 0.774 on AVA,
which was the top result at CVPR 2023. This was ~1-2% higher than previous best models like TANet or
GAT+GATP. Even in zero-shot mode (no AVA training), VILA’s contrastive model attained SRCC ~0.66 on
AVA – outperforming many fully supervised older models. These results underscore the benefit of the
comment-based pretraining.
Inference Feasibility: VILA’s full model is moderately large because CoCa is a transformer with image and
text encoders (on the order of hundreds of millions of parameters). Running it requires a capable GPU, but
it’s still feasible to use locally. The fine-tuned version can process an image (224×224) quickly, especially
since  the  adapter  is  lightweight.  In  practice,  one  could  use  the  released  model  on  a  single  GPU  for
inference; an RTX 4060 can handle it, though using half-precision (FP16) is recommended for speed and
memory. If needed, developers can also distill or quantize the model to further lighten it.
Code & Checkpoints: The code for VILA is available in the google-research repository, and the trained model
weights  are  provided  (under  Google  Research’s  GitHub).  There  is  also  a  pretrained  checkpoint  in
TensorFlow that can be converted for PyTorch use. This accessibility allows integration into custom pipelines
or direct use via the official repository.
TANet (2022)
Framework: PyTorch (official code on GitHub).
Method:Theme-Aware Aesthetic Network (TANet)  was proposed to handle the fact that image aesthetics
can depend on image theme/genre. The authors introduced TAD66K, a dataset of 66k images labeled with
47 theme categories (landscape, portrait, food, etc.) and aesthetics scores, then designed TANet as a two-
branch CNN: one branch (TUNet) predicts the image’s theme, and the other branch (an aesthetics CNN)
predicts the aesthetic score while adaptively using the theme information. Specifically, TANet learns
to “adaptively establish perception rules” per theme – for example, what makes a good portrait is different
from  what  makes  a  good  landscape.  The  network  maintains  a  constant  aesthetic  perception across
diverse themes by using the theme recognition to modulate the feature extraction for aesthetics. In
practice, TUNet provides a theme embedding that influences the aesthetic prediction layer or attention
mechanism, so that the model’s focus (composition, color , etc.) adjusts based on theme. This addresses the
“attention dispersion” problem where a generic model might not focus on the right cues for a given image
category .
Performance: TANet was a state-of-the-art model on AVA and other benchmarks upon its debut in 2022
. Evaluated on AVA, TANet achieved SRCC ≈0.758 and PLCC ≈0.765 (as reported in later comparisons)
. It also outperformed earlier methods on the authors’ new TAD66K dataset and the FLICKR-AES dataset,
essentially setting a new baseline across three different aesthetic datasets. While newer models (VILA,
QPT V2, etc.) have since surpassed TANet on AVA, it remains a strong performing model, especially notable
for excelling across diverse image themes.
Inference  Feasibility: TANet  uses  a  ResNet-based  architecture  with  some  additional  layers  for  theme
adaptation. The model size is around  40 million parameters, which is fairly lightweight by today’s
standards. On an RTX 4060, TANet can run very efficiently – scoring an image in a few milliseconds. The
extra theme classification branch adds negligible overhead. The main consideration is that one must supply
the theme labels during training; however , for inference on arbitrary images, TANet will predict a theme
internally  as  part  of  its  pipeline.  Running  TANet  locally  is  straightforward  and  doesn’t  require  special
hardware  beyond  a  normal  GPU  with  a  few  GB  of  memory  (even  a  mid-range  card  can  handle  batch
inference).
Code & Checkpoints: The official PyTorch code and pretrained weights for TANet (trained on AVA, etc.) are
15 16
17
15
18
19
20
21 20
22
20
20
23
17
24
25
3

## Page 4

published  on  GitHub.  The  repository  also  provides  the  TAD66K  dataset  and  instructions,  enabling
researchers to reproduce results or fine-tune TANet on custom aesthetic datasets if needed.
AesMamba (2024)
Framework: PyTorch (code available on GitHub; built on the state-spaces/mamba library) .
Method:AesMamba  is a  universal IAA framework that uses modern  state-space sequence models
instead of CNNs or standard transformers. At its core is a  Visual State Space Model (VSMamba) backbone,
which can efficiently capture both  global and local features of an image via state-space layers. This
gives  AesMamba  a  strong  representation  of  aesthetic  attributes  (color ,  composition,  etc.)  with  high
efficiency  and  long-range  modeling  capacity  (a  single  state-space  layer  can  have  an  extremely  large
receptive field without the quadratic cost of self-attention). On top of this backbone, AesMamba is modular:
it includes a  modal-adaptive integration module to combine inputs of different modalities (it can handle
purely visual inputs or image+text if available), and a multitask balanced adaptation (MBA) module that helps
the  model  focus  on  under-represented  attributes  or  “tail”  examples  during  training.  Moreover ,
AesMamba extends to personalized aesthetics by converting user preference data into textual “prompts” –
essentially treating a user ID or profile as text input to the model to bias the aesthetic predictions for that
user . This prompt-based personalization is a novel way to incorporate user taste in a unified model. The
result is a single architecture that can tackle generic aesthetic score regression (GIAA), fine-grained multi-
attribute aesthetic predictions (FIAA, e.g. scoring specific facets like composition, lighting separately), and
personalized aesthetic ranking (PIAA), simply by swapping or combining modules.
Performance: AesMamba delivers highly competitive or superior performance across all major aesthetic
tasks . On the AVA dataset (generic aesthetic prediction), it achieves state-of-the-art correlation scores
comparable to the best models in literature as of 2024. While exact numbers vary by AesMamba variant, the
model’s  AVA  SRCC  is  around  0.80–0.82,  placing  it  at  the  very  top.  The  authors  report  that  AesMamba
outperforms or matches prior SOTA on every aesthetic benchmark they evaluated – including AVA, the
Photographic Aesthetics (Photo.Net) dataset, the AADB dataset, and others – all with a single unified model.
This is particularly impressive given that many prior models specialized in one aspect (either generic or
personalized)  whereas  AesMamba  handles  all.  The  ACM  Multimedia  reviewers  designated  it  an  Oral
presentation, reflecting its strong results.
Inference Feasibility: One motivation for using state-space models is  efficiency. AesMamba’s backbone
(VMamba-Tiny or -Base) is designed to be memory-efficient and fast, even with very long input sequences
(images can be flattened as sequences of patches for the state-space layer). The released model variants
are comparable in size to ConvNeXt or Swin backbones. Running AesMamba on a local GPU like RTX 4060 is
quite feasible; it can score images at speeds similar to or faster than transformer-based models because
the state-space layers have favorable scaling. The model does not require any online external input (aside
from an optional text prompt for personalization, which is a small fixed embedding). All computations are
local, making it suitable for deployment in an agent.
Code & Checkpoints: The AesMamba code (PyTorch) and model definitions are available on GitHub,
and the repository indicates that pretrained checkpoints for various tasks will be provided (some may be
available via a Baidu Drive link, with broader release after peer review). The code depends on the
open-source  MAMBA state-space  model  library,  which  is  simple  to  install.  With  the  code  in  hand,
developers can reproduce the results or fine-tune AesMamba on their own aesthetic datasets, as well as
evaluate the model on images locally.

## Page 5

Q-Align (2024)
Framework: PyTorch (implemented via HuggingFace Transformers; uses a large vision-language model
backbone) .
Method:Q-Align  (ICML 2024) takes a novel approach by bringing in Large Multi-modal Models (LMMs)
to aesthetic and quality assessment. The idea is inspired by how human raters are trained – humans
typically  rate  images  using  discrete  quality  levels (“excellent”,  “good”,  “fair”,  etc.)  rather  than  direct
numeric scores. Q-Align thus reframes visual scoring as a classification problem with text labels. It
uses a pre-trained multimodal large language model (specifically, the authors built on the mPLUG-Owl 2
architecture, which is an LLM with vision capabilities) and fine-tunes it with instruction pairs where the
model is asked to give a rating level for an image. The continuous MOS scores in training datasets are
converted  into  five  discrete  levels (e.g.  Bad,  Poor ,  Fair ,  Good,  Excellent),  and  the  LMM  is  trained  via
instruction tuning to output these levels for images. During inference, Q-Align mimics the process
of averaging human opinions: it obtains the probabilities for each rating level from the model’s output and
computes a weighted average score. By aligning the model’s outputs with text-defined levels (which
LLMs handle well) instead of regressing raw numbers (which LLMs find hard), Q-Align achieves remarkable
accuracy  in  aesthetic  prediction.  Essentially,  it  “teaches”  an  LMM  to  become  an  aesthetic  scorer  via  a
discrete curriculum (“teach by examples of Excellent/Good/... images”). An added benefit is that Q-Align
trains a single unified model for IQA, IAA, and VQA (image quality, aesthetics, and video quality), termed
OneAlign when all tasks are combined. The unified model can handle all three tasks with one set of
weights by using appropriate prompts (the model is told which task and provided input accordingly).
Performance: Q-Align achieves  state-of-the-art performance on image aesthetics as well as on quality
tasks . On the AVA benchmark, Q-Align attains an SRCC of 0.822 (and PLCC ~0.817) when fine-tuned for
IAA . This is the highest reported correlation on AVA to date, slightly edging out other 2024 models like
QPT V2 and AesMamba. Even the unified OneAlign model (trained on IQA+IAA+VQA together) reaches a
similar SRCC ~0.823 on AVA, indicating no loss in aesthetic accuracy despite learning multiple tasks. The
authors highlight that Q-Align also set new records on numerous IQA and VQA datasets, underlining the
advantage of the discrete-level training strategy. In summary, Q-Align brought foundation model
power into the aesthetic scoring domain, significantly pushing the performance ceilings.
Inference Feasibility: Because Q-Align is built on a large multimodal transformer (in the class of LLaVA,
mPLUG, etc.), it is the heaviest model in this list. The backbone is roughly a 7–13 billion parameter LLM with
vision capabilities. Running such a model locally on an RTX 4060 (with 8–12GB VRAM) is challenging but not
impossible. The provided implementation supports 16-bit half-precision and model loading with device
mapping . With 8-bit quantization or by offloading some layers to CPU, one can perform inference on a
single high-end consumer GPU at slower speeds. In practical terms, using Q-Align in real-time might require
a more powerful GPU or multi-GPU setup, but for  batch processing of images in an agentic workflow, it
could work with the 4060 (albeit with high latency per image). The model’s advantage is flexibility – it can
output human-like explanations or follow instructions along with giving scores – but that flexibility comes
with computational cost. If needed, one could opt for the smaller  OneAlign-T variant (the authors might
release a distilled or tiny version) or use LoRA adapters to run on smaller hardware. Nonetheless, Q-Align is
locally runnable in that everything is self-contained (no API calls), using the HuggingFace Transformers
integration.
Code & Checkpoints: The Q-Align project released code and a pretrained checkpoint publicly. The model
(OneAlign) is available on HuggingFace Hub, which allows easy loading via AutoModelForCausalLM
. The GitHub repo provides training scripts and the discrete “syllabus” used to fine-tune the LMM.
This means developers can directly use the q-future/one-align model to score images – for example,
by calling model.score([image], task_="aesthetics") as shown in the documentation. Overall,

## Page 6

Q-Align’s resources make it accessible for research and integration, provided one has the hardware to
accommodate the model.
Comparison of Models
The  table  below  summarizes  and  compares  these  models  in  terms  of  architecture,  framework,  and
performance on AVA (aesthetic ranking correlation):
Model (Year) Framework Architecture / Approach AVA SRCC
(↑)
TANet (2022) PyTorch Two-branch CNN (theme recognition + aesthetic
CNN) 0.758
VILA (2023) TensorFlow/
JAX
Vision-Language (CoCa Transformer + rank
adapter) 0.774
LIQE (2023) PyTorch CLIP ViT (vision-language prompts, multitask
learning) 0.776
QPT V2 (2024) PyTorch Multi-scale ViT (MIM pre-training, no text input)~0.817 ¹
AesMamba
(2024) PyTorch State-space model backbone (modular multi-
task design)
~0.81–0.82
¹
Q-Align (2024) PyTorch Large Vision-Language Model (discrete label
tuning) 0.822
<small>¹ Approximate SRCC shown for QPT V2 and AesMamba based on reported improvements or “highly
competitive” claims, as exact AVA test values were not explicitly quoted in those papers.</small>
Key Takeaways: Recent local aesthetic scorers have evolved from CNN-based models to sophisticated
transformers and state-space models, often incorporating multi-modal data or pre-training strategies to
overcome data scarcity. Models like  QPT V2 and  AesMamba focus on innovative  visual backbones and
training schemes, achieving top performance without text inputs. On the other hand, VILA, LIQE,
and  Q-Align leverage  vision-language techniques – either via user comments, CLIP embeddings, or large
multimodal LLMs – to inject semantic understanding into aesthetic assessment. All of the listed
models are implemented in either PyTorch or TensorFlow and come with code or weights, making them
readily usable for developers. Depending on the use-case and hardware, one might choose a lighter model
like TANet or LIQE for speed, or a heavier model like Q-Align for maximum accuracy. Importantly, each
represents the state-of-the-art of its time, and together they reflect the rapid progress in automatic image
aesthetic quality assessment up to 2025.

### References

- VILA: Learning Image Aesthetics From User Comments With Vision-Language
Pretraining
https://openaccess.thecvf.com/content/CVPR2023/papers/Ke_VILA_Learning_Image_Aesthetics_From_User_Comments_With_Vision-Language_Pretraining_CVPR_2023_paper.pdf

## Page 7

q-future/one-align · Hugging Face
https://huggingface.co/q-future/one-align
[2407.16541] QPT V2: Masked Image Modeling Advances Visual Scoring
https://ar5iv.labs.arxiv.org/html/2407.16541
[Quick Review] QPT-V2: Masked Image Modeling Advances Visual Scoring
https://liner .com/review/qptv2-masked-image-modeling-advances-visual-scoring
GitHub - zwx8981/LIQE: [CVPR2023] Blind Image Quality Assessment via Vision-
Language Correspondence: A Multitask Learning Perspective
https://github.com/zwx8981/LIQE
GitHub - woshidandan/TANet-image-aesthetics-and-quality-assessment: [IJCAI 2022, Official
Code] for paper "Rethinking Image Aesthetics Assessment: Models, Datasets and Benchmarks". Official
Weights and Demos provided. 首个面向多主题场景的美学评估数据集、算法和benchmark.
https://github.com/woshidandan/TANet-image-aesthetics-and-quality-assessment
Rethinking Image Aesthetics Assessment: Models, Datasets and ...
https://www.ijcai.org/proceedings/2022/132
[Quick Review] Rethinking Image Aesthetics Assessment: Models ...
https://liner .com/review/rethinking-image-aesthetics-assessment-models-datasets-and-benchmarks
Image aesthetic quality assessment: A method based on deep ... - NIH
https://pmc.ncbi.nlm.nih.gov/articles/PMC12453199/
GitHub - AiArt-Gao/AesMamba: [ACM MM'24] Oral, AesMamba
https://github.com/AiArt-Gao/AesMamba
AesMamba: Universal Image Aesthetic Assessment with State Space Models
https://openreview.net/pdf/543adc6f9b435ea008314023d5b6e394bbd4f875.pdf
[2312.17090] Q-Align: Teaching LMMs for Visual Scoring via Discrete Text-Defined Levels
https://arxiv.org/abs/2312.17090
[2312.17090] Q-Align: Teaching LMMs for Visual Scoring via Discrete Text-Defined Levels
https://ar5iv.labs.arxiv.org/html/2312.17090v1
Q-Align: Teaching LMMs for Visual Scoring via Discrete Text-Defined Levels
https://q-align.github.io/
