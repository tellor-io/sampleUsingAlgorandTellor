from pyteal import *


# global variables
tellor_app_id = Bytes("tellor_app_id")
tellor_query_id = Bytes("tellor_query_id")
tellor_value = Bytes("tellor_value")

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
    changes the current value recorded in the contract
    solidity equivalent: submitValue()

    Txn args:
    0) will always equal "bid" (in order to route to this method)
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
            Approve(),
        ]
    )


def withdraw():
    """
    sends the reporter's stake back to their address
    removes their permission to report data

    solidity equivalent: withdrawStake()

    Txn args:
    0) will always equal "withdraw"

    """
    return Seq(
        [
            # assert the reporter is staked
            Assert(
                And(
                    Txn.sender() == App.globalGet(reporter),
                    App.globalGet(staking_status) == Int(1),
                )
            ),
            # change staking status to unstaked
            App.globalPut(staking_status, Int(0)),
            # send funds back to reporter (the sender) w/ inner tx
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.Payment,
                    # TxnField.amount: App.globalGet(stake_amount),
                    TxnField.close_remainder_to: App.globalGet(reporter),
                }
            ),
            InnerTxnBuilder.Submit(),
            Approve(),
        ]
    )


def vote():
    """
    allows the governance contract to approve or deny a new value
    if governance approves, the num_votes counter increases by 1
    if governance rejects, the reporter's ALGO stake is sent to
    the governance contract

    solidity equivalent: slashMiner()

    Args:
    0) will always be equal to "vote"
    1) decision -- 1 is approval, 0 is rejection
    """

    def slash_reporter():
        """
        - transfers reporter's stake to governance contract
        - removes their permission to submit data (reporting)
        """
        return Seq(
            [
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields(
                    {
                        TxnField.type_enum: TxnType.Payment,
                        TxnField.close_remainder_to: App.globalGet(governance_address),
                    }
                ),
                InnerTxnBuilder.Submit(),
                App.globalPut(staking_status, Int(0)),
            ]
        )

    def reward_reporter():
        """increase reporter's number of recorded reports"""
        return App.globalPut(num_reports, App.globalGet(num_reports) + Int(1))

    return Seq(
        [
            Assert(is_governance),
            Cond(
                [And(Btoi(Txn.application_args[1]) != Int(0), Btoi(Txn.application_args[1]) != Int(1)), Reject()],
                [Btoi(Txn.application_args[1]) == Int(1), reward_reporter()],
                [Btoi(Txn.application_args[1]) == Int(0), slash_reporter()],
            ),
            Approve(),
        ]
    )


def stake():
    """
    gives permission to reporter to report values
    changes permission when the contract
    receives the reporter's stake

    Args:
    0) will always be equal to "stake"
    """

    on_stake_tx_index = Txn.group_index() - Int(1)

    # enforced two part Gtxn: 1) send token to contract, 2) stake
    return Seq(
        [
            Assert(
                And(
                    App.globalGet(reporter) == Bytes(""),
                    Gtxn[on_stake_tx_index].sender() == Txn.sender(),
                    Gtxn[on_stake_tx_index].receiver() == Global.current_application_address(),
                    Gtxn[on_stake_tx_index].amount() == App.globalGet(stake_amount),
                    Gtxn[on_stake_tx_index].type_enum() == TxnType.Payment,
                ),
            ),
            App.globalPut(staking_status, Int(1)),
            App.globalPut(reporter, Gtxn[on_stake_tx_index].sender()),
            Approve(),
        ]
    )


def handle_method():
    """
    calls the appropriate contract method if
    a NoOp transaction is sent to the contract
    """
    contract_method = Txn.application_args[0]
    return Cond(
        [contract_method == Bytes("stake"), stake()],
        [contract_method == Bytes("report"), report()],
        [contract_method == Bytes("vote"), vote()],
        [contract_method == Bytes("withdraw"), withdraw()],
    )
