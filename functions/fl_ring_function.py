from pathlib import Path
from types import SimpleNamespace
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from pathlib import Path
from types import SimpleNamespace
from syftbox.lib import Client, SyftPermission
from torch.utils.data import DataLoader, TensorDataset
import shutil
import os


class SimpleNN(nn.Module):
    def __init__(self):
        super(SimpleNN, self).__init__()
        self.fc1 = nn.Linear(28 * 28, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x):
        x = x.view(-1, 28 * 28)
        x = torch.relu(self.fc1(x))
        x = self.fc2(x)
        return x


def ring_function(ring_data: SimpleNamespace, secret_path: Path):
    client = Client.load()
    dataset_path = ""
    with open(secret_path, "r") as secret_file:
        dataset_path = secret_file.read().strip()

    if ring_data.current_index >= len(ring_data.ring) - 1:
        done_pipeline_path: Path = (
            Path(client.datasite_path) / "app_pipelines" / "fl_ring" / "done"
        )
        destination_datasite_path = Path(client.sync_folder) / client.email 
        new_model_path = (
            destination_datasite_path
            / "app_pipelines"
            / "fl_ring"
            / "running"
            / ring_data.model
        )
        final_data_json_path = (
            destination_datasite_path
            / "app_pipelines"
            / "fl_ring"
            / "running"
            / "data.json" 
        )

        shutil.move(new_model_path, str(done_pipeline_path))
        shutil.move(final_data_json_path, str(done_pipeline_path))
        return 0
    
    model = SimpleNN()  # Initialize model

    # Load serialized model if present
    if hasattr(ring_data, "model"):
        state_dict = torch.load(ring_data.model)
        model.load_state_dict(state_dict)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=float(ring_data.learning_rate))

    dataset_path_files = [f for f in os.listdir(dataset_path) if f.endswith('.pt')]
    running_loss = 0 
    if len(dataset_path_files) > 0:
        for dataset_file in dataset_path_files:

            # load mnist dataset
            transform = transforms.Compose([transforms.ToTensor()])

            # load the saved mnist subset
            images, labels = torch.load(dataset_path + '/' + dataset_file)

            # create a tensordataset
            dataset = TensorDataset(images, labels)

            # create a dataloader for the dataset
            train_loader = DataLoader(dataset, batch_size=32, shuffle=True)

            print("\n\n training...\n\n ")
            # training loop
            for epoch in range(int(ring_data.iterations)):
                running_loss = 0
                for i, (images, labels) in enumerate(train_loader, 1):
                    optimizer.zero_grad()
                    outputs = model(images)
                    loss = criterion(outputs, labels)
                    loss.backward()
                    optimizer.step()

                    # accumulate loss
                    running_loss += loss.item()

                    # print loss every 200 epochs
                    if i % 200 == 0:
                        print(
                            f"epoch [{epoch+1}/{ring_data.iterations}], step [{i}/{len(train_loader)}], loss: {running_loss/200:.4f}"
                        )
                        running_loss = 0.0

        print("\n\n done...\n\n ")

        # evaluation
        correct = 0
        total = 0
        with torch.no_grad():
            for images, labels in train_loader:
                outputs = model(images)
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()

        accuracy = 100 * correct / total
        print(f'accuracy of the model on the test dataset: {accuracy:.2f}%')
    else:
        print("\n\n\n No data found, skipping to the next person!\n\n")

    next_index = ring_data.current_index + 1
    next_person = ring_data.ring[next_index]

    destination_datasite_path = Path(client.sync_folder) / next_person
    new_model_path = (
        destination_datasite_path
        / "app_pipelines"
        / "fl_ring"
        / "running"
        / ring_data.model
    )
   
    iterations = 0
    if len(dataset_path_files) > 0:
        iterations = ring_data.iterations

    print(f"\n\n Saving it in {str(new_model_path)}\n\n")
    # Serialize the model
    os.makedirs(os.path.dirname(str(new_model_path)), exist_ok=True)
    torch.save(model.state_dict(), str(new_model_path))
    return {"loss": running_loss, "iterations": ring_data.data['iterations'] + iterations} 
