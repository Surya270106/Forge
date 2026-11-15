from forgebench import retry_delay


def retry_schedule(attempts: int) -> list[int]:
    return [retry_delay(index) for index in range(attempts)]
