from fileinput import close
from pyteal import *


# global variables
tellor_app_id = Bytes("tellor_app_id")
tellor_query_id = Bytes("tellor_query_id")
tellor_value = Bytes("tellor_value")
bidders = Bytes("bidders")

"""
functions listed in alphabetical order

method arguments must be passed in provided order
as they are expected by the contract logic
to follow that order

"""


def create():
    """
    does setup of Tellor contract on Alogrand
    solidity equivalent: constructor()

    args:
    0) tellor app id
    1) tellor query id

    """
    return Seq(
        [
            # TODO assert application args length is correct
            App.globalPut(tellor_app_id, Txn.application_args[0]),
            App.globalPut(tellor_query_id, Txn.application_args[1]),
            Approve(),
        ]
    )


def bid():
    """
    bid 1 algo to place a prediction on the value reported to the tellor oracle

    Txn args:
    1) prediction (int) -- the price of the asset the bidder predicts
    """
    on_stake_tx_index = Txn.group_index() - Int(1)

    # enforced two part Gtxn: 1) send token to contract, 2) stake
    return Seq(
        [
            Assert(
                And(
                    Gtxn[on_stake_tx_index].sender() == Txn.sender(),
                    Gtxn[on_stake_tx_index].receiver() == Global.current_application_address(),
                    Gtxn[on_stake_tx_index].amount() == Int(1000), #1 algo
                    Gtxn[on_stake_tx_index].type_enum() == TxnType.Payment,
                ),
            ),
            #record bid amount
            #bids are 1 algo
            App.globalPut(Txn.sender(), Int(1)),
            If(
                App.globalGet(bidders) == Bytes(""),
                App.globalPut(bidders, Txn.sender()),
                App.globalPut(
                    bidders,
                    Concat(App.globalGet(bidders), Txn.sender())
                    )
                ),
            Approve(),
        ]
    )

def settle():
    """
    reads tellor value, calculates closest prediction, rewards winner

    called on CloseOut transaction
    """
    
    actual = App.globalGetEx(App.globalGet(tellor_app_id), Bytes("value"))
    counter = ScratchVar(TealType.uint64)
    closeness = ScratchVar(TealType.uint64)
    winner = ScratchVar(TealType.bytes)
    prediction = ScratchVar(TealType.uint64)
    # while counter < len(str(App.globalGet(bidders))):
    #     winner = Extract(App.globalGet(bidders), Int(counter), Int(32))
    #     prediction = App.globalGet(winner)
    #     current_closeness = abs(prediction - actual)

    #     if current_closeness < closeness:
    #         closeness = current_closeness
    

    return Seq(
        [
            Assert(
                Len(App.globalGet(bidders)) >= Int(64)
            ),
            actual,
            prediction.store(Int(0)),
            counter.store(Int(0)),
            closeness.store(Int(2**16)),
            winner.store(Extract(App.globalGet(bidders), counter.load(), Int(32))),
            While(counter.load() < Len(App.globalGet(bidders))).Do(
                Seq([
                    If(
                        App.globalGet(winner.load()) < closeness.load(),
                        winner.store(Extract(App.globalGet(bidders), counter.load(), Int(32)))
                    ),
                    counter.store(counter.load() + Int(32))
                ])

            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.Payment,
                    TxnField.close_remainder_to: App.globalGet(winner.load()),
                }
            ),
            InnerTxnBuilder.Submit(),
            Approve(),
    ]
    )