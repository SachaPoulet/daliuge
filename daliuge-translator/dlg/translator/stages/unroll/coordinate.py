from dataclasses import dataclass, field


@dataclass(frozen=True)
class InstanceId:
    path: tuple[int, ...]
    group_key: tuple[int, ...] = ()
    _wire: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if self._wire:
            return

        path = "-".join(str(value) for value in self.path)

        if self.group_key:
            group_key = "-".join(str(value) for value in self.group_key)
            path = f"{path}${group_key}"

        object.__setattr__(self, "_wire", path)

    def child(self, index: int) -> "InstanceId":
        return InstanceId(
            path=self.path + (index,),
            group_key=self.group_key,
            _wire=f"{self}-{index}",
        )

    def with_group_key(self, group_key: tuple[int, ...]) -> "InstanceId":
        group_key_string = "-".join(str(value) for value in group_key)

        return InstanceId(
            path=self.path,
            group_key=group_key,
            _wire=f"{self}${group_key_string}",
        )

    def __str__(self) -> str:
        return self._wire
