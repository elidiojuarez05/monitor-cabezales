from image_processor import process_image
from crud import save_test
import os

IMAGE_FOLDER = "storage/images"

def process_new_images():

    for file in os.listdir(IMAGE_FOLDER):

        path = os.path.join(IMAGE_FOLDER,file)

        result = process_image(path)

        save_test(
            machine="Machine_1",
            shift="Turno 1",
            health=result["health"],
            active=result["active"],
            failed=result["failed"],
            image_path=path
        )