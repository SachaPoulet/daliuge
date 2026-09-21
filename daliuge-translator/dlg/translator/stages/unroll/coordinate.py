from dataclasses import dataclass


@dataclass(frozen=True)
class InstanceId:
    path: tuple[int, ...]
    group_key: tuple[int, ...] = ()

    def child(self, index: int) -> "InstanceId":
        return InstanceId(
            path=self.path + (index,),
            group_key=self.group_key,
        )

    def __str__(self) -> str:
        path = "-".join(str(value) for value in self.path)

        if not self.group_key:
            return path

        group_key = "-".join(str(value) for value in self.group_key)
        return f"{path}${group_key}"