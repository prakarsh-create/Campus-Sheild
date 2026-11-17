from functools import lru_cache
from io import BytesIO
from threading import Lock


class InvalidImageError(ValueError):
    pass


class ImageModelError(RuntimeError):
    pass


_MODEL_LOCK = Lock()


@lru_cache(maxsize=1)
def _load_model():
    with _MODEL_LOCK:
        try:
            import torch
            from torch import nn
            from torchvision.models import ResNet18_Weights, resnet18

            weights = ResNet18_Weights.DEFAULT
            model = resnet18(weights=weights)
            model.fc = nn.Identity()
            model.eval()
            return torch, model, weights.transforms()
        except Exception as exc:
            raise ImageModelError("Could not load pretrained ResNet18") from exc


def extract_embedding(image_data: bytes) -> list[float]:
    try:
        from PIL import Image, UnidentifiedImageError

        try:
            image = Image.open(BytesIO(image_data)).convert("RGB")
        except (UnidentifiedImageError, OSError) as exc:
            raise InvalidImageError("Unsupported or corrupt image") from exc
    except ImportError as exc:
        raise ImageModelError("Pillow is not installed") from exc

    torch, model, preprocess = _load_model()
    try:
        with torch.inference_mode():
            features = model(preprocess(image).unsqueeze(0))
            features = torch.nn.functional.normalize(features, p=2, dim=1)
        return features[0].tolist()
    except Exception as exc:
        raise ImageModelError("Could not extract image features") from exc
